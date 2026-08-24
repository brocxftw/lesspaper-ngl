"""RAG / ask integration tests with mocked chat adapter."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.base import (
    AIProviderAdapter,
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    ModelCapabilities,
)
from lesspaper_ngl.models import DocumentChunk


@dataclass
class _MockLocalChatAdapter(AIProviderAdapter):
    chunk_id: uuid.UUID
    provider_name: str = "mock-local"
    is_local: bool = True

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(supports_chat=True)

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        return ChatResult(
            content=f"The loan amount is RM 420,000 [chunk:{self.chunk_id}].",
            model=model or "mock-local",
            input_tokens=100,
            output_tokens=20,
        )

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        return EmbeddingResult(embeddings=[], model=model or "mock")

    async def test_connection(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


@dataclass
class _MockInsufficientAdapter(AIProviderAdapter):
    provider_name: str = "mock-insufficient"
    is_local: bool = True

    @property
    def capabilities(self) -> ModelCapabilities:
        return ModelCapabilities(supports_chat=True)

    async def chat(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> ChatResult:
        return ChatResult(content="INSUFFICIENT_EVIDENCE", model=model or "mock")

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        return EmbeddingResult(embeddings=[], model=model or "mock")

    async def test_connection(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


async def _setup_local_chat_provider(auth_client: AsyncClient) -> str:
    provider = await auth_client.post(
        "/api/ai/providers",
        json={
            "name": "local-chat",
            "kind": "ollama",
            "base_url": "http://localhost:11434",
            "is_local": True,
            "chat_model": "llama-test",
        },
    )
    assert provider.status_code == 201
    provider_id = provider.json()["id"]

    policy = await auth_client.patch(
        "/api/ai/policy",
        json={
            "chat_provider_id": provider_id,
            "warn_before_remote": False,
        },
    )
    assert policy.status_code == 200
    return provider_id


@pytest.mark.asyncio
async def test_ask_returns_answer_with_valid_citations(
    auth_client: AsyncClient,
    uploaded_txt_doc: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _setup_local_chat_provider(auth_client)

    chunk = (
        await db_session.execute(
            select(DocumentChunk).where(
                DocumentChunk.document_id == uuid.UUID(uploaded_txt_doc["id"])
            )
        )
    ).scalars().first()
    assert chunk is not None

    monkeypatch.setattr(
        "lesspaper_ngl.api.documents.get_adapter",
        lambda provider, api_key=None: _MockLocalChatAdapter(chunk_id=chunk.id),
    )

    response = await auth_client.post(
        f"/api/documents/{uploaded_txt_doc['id']}/ask",
        json={"question": "What is the LPPSA loan amount?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["insufficient_evidence"] is False
    assert "420" in body["answer"]
    assert body["citations"]
    assert str(chunk.id) in body["answer"] or any(
        str(c["chunk_id"]) == str(chunk.id) for c in body["citations"]
    )


@pytest.mark.asyncio
async def test_ask_insufficient_evidence_path(
    auth_client: AsyncClient,
    uploaded_txt_doc: dict,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _setup_local_chat_provider(auth_client)
    monkeypatch.setattr(
        "lesspaper_ngl.api.documents.get_adapter",
        lambda provider, api_key=None: _MockInsufficientAdapter(),
    )

    response = await auth_client.post(
        f"/api/documents/{uploaded_txt_doc['id']}/ask",
        json={"question": "What is the borrower's shoe size?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["insufficient_evidence"] is True
    assert body["citations"] == []


@pytest.mark.asyncio
async def test_workspace_ask_search_snapshot_respects_folder(
    auth_client: AsyncClient,
    uploaded_txt_doc: dict,
    sample_txt_path,
    run_extraction,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _setup_local_chat_provider(auth_client)

    folder = await auth_client.post("/api/folders", json={"name": "Ask Scope"})
    assert folder.status_code == 201
    folder_id = folder.json()["id"]

    scoped_path = sample_txt_path.parent / "ask-scoped-sample.txt"
    scoped_path.write_bytes(
        b"Scoped folder document about LPPSA tenure 30 years RM 500000.\n"
    )
    with scoped_path.open("rb") as fh:
        scoped = await auth_client.post(
            "/api/documents/upload",
            data={"folder_id": folder_id},
            files={"file": ("scoped-ask.txt", fh, "text/plain")},
        )
    assert scoped.status_code == 201
    scoped_id = scoped.json()["id"]
    await run_extraction(uuid.UUID(scoped_id))

    chunk = (
        await db_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == uuid.UUID(scoped_id))
        )
    ).scalars().first()
    assert chunk is not None

    monkeypatch.setattr(
        "lesspaper_ngl.api.ask.get_adapter",
        lambda provider, api_key=None: _MockLocalChatAdapter(chunk_id=chunk.id),
    )

    response = await auth_client.post(
        "/api/ask",
        json={
            "question": "What is the LPPSA tenure?",
            "scope": "search",
            "search": {
                "query": "LPPSA",
                "mode": "keyword",
                "folder_id": folder_id,
                "include_descendants": False,
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["insufficient_evidence"] is False
    assert body["citations"]
    citation_docs = {c["document_id"] for c in body["citations"]}
    assert scoped_id in citation_docs
    assert uploaded_txt_doc["id"] not in citation_docs


@pytest.mark.asyncio
async def test_workspace_ask_requires_confirm_remote(
    auth_client: AsyncClient,
) -> None:
    chat = await auth_client.post(
        "/api/ai/providers",
        json={
            "name": "remote-chat-ask",
            "kind": "openai_compatible",
            "base_url": "https://api.example.com/v1",
            "is_local": False,
            "chat_model": "gpt-test",
            "supports_embeddings": False,
        },
    )
    assert chat.status_code == 201
    chat_id = chat.json()["id"]

    policy = await auth_client.patch(
        "/api/ai/policy",
        json={
            "privacy_mode": "standard",
            "chat_provider_id": chat_id,
            "warn_before_remote": True,
        },
    )
    assert policy.status_code == 200

    blocked = await auth_client.post(
        "/api/ask",
        json={
            "question": "Summarise the library",
            "scope": "library",
            "confirm_remote": False,
        },
    )
    assert blocked.status_code == 403
    assert blocked.json()["code"] == "privacy_violation"
