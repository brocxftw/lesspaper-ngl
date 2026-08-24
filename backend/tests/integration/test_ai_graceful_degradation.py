"""AI optional / graceful degradation: soft-fail suggestions + health API."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.base import (
    AIProviderAdapter,
    AIProviderError,
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    ModelCapabilities,
)
from lesspaper_ngl.models import AIProvider, Document, Job, JobStatus, JobType, ProcessingStatus
from lesspaper_ngl.workers.processor import process_metadata_suggestion, process_text_extraction


@dataclass
class _FailingAdapter(AIProviderAdapter):
    """Non-transient AI failure (auth) — should soft-skip, not fail the document."""

    provider_name: str = "mock-failing"
    is_local: bool = True
    message: str = "invalid api key"
    status_code: int = 401

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
        del messages, model, max_tokens, temperature
        raise AIProviderError(self.message, status_code=self.status_code)

    async def embed(
        self,
        texts: list[str],
        *,
        model: str | None = None,
    ) -> EmbeddingResult:
        del texts, model
        return EmbeddingResult(embeddings=[], model="mock")

    async def test_connection(self) -> bool:
        return False

    async def aclose(self) -> None:
        return None


async def _enable_auto_tagging(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> str:
    provider = await auth_client.post(
        "/api/ai/providers",
        json={
            "name": "soft-fail-chat",
            "kind": "ollama",
            "base_url": "http://localhost:11434",
            "is_local": True,
            "chat_model": "mock-failing",
        },
    )
    assert provider.status_code == 201, provider.text
    provider_id = provider.json()["id"]

    # Suggestion enqueue requires a successful health probe.
    row = await db_session.get(AIProvider, uuid.UUID(provider_id))
    assert row is not None
    row.last_probe_status = "available"
    await db_session.commit()

    policy = await auth_client.patch(
        "/api/ai/policy",
        json={
            "privacy_mode": "local_only",
            "chat_provider_id": provider_id,
            "auto_tagging": True,
            "auto_enrichment": False,
        },
    )
    assert policy.status_code == 200, policy.text
    return provider_id


@pytest.mark.asyncio
async def test_ai_health_endpoint_returns_per_capability(
    auth_client: AsyncClient,
) -> None:
    response = await auth_client.get("/api/ai/health")
    assert response.status_code == 200, response.text
    body = response.json()
    for key in ("ocr", "indexing", "embedding", "chat"):
        assert key in body
        assert body[key]["status"] in {
            "available",
            "unavailable",
            "checking",
            "not_configured",
        }
    assert "auto_tagging" in body
    assert "auto_enrichment" in body
    # OCR_ENABLED=false in tests → not_configured
    assert body["ocr"]["status"] == "not_configured"
    # No providers assigned by default after truncate → not_configured
    assert body["indexing"]["status"] == "not_configured"
    assert body["embedding"]["status"] == "not_configured"
    assert body["chat"]["status"] == "not_configured"


@pytest.mark.asyncio
async def test_ai_health_reflects_probe_independence(
    auth_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    from lesspaper_ngl.models import AIProvider

    provider = await auth_client.post(
        "/api/ai/providers",
        json={
            "name": "health-probe-provider",
            "kind": "openai_compatible",
            "base_url": "http://localhost:9999/v1",
            "is_local": True,
            "chat_model": "chat-x",
            "embedding_model": "embed-x",
            "supports_embeddings": True,
        },
    )
    assert provider.status_code == 201, provider.text
    provider_id = uuid.UUID(provider.json()["id"])

    for role, model in (
        ("indexing", "index-model"),
        ("chat", "chat-model"),
        ("embedding", "embed-model"),
    ):
        patched = await auth_client.patch(
            "/api/ai/assignments",
            json={"role": role, "provider_id": str(provider_id), "model": model},
        )
        assert patched.status_code == 200, patched.text

    row = await db_session.get(AIProvider, provider_id)
    assert row is not None
    row.last_probe_status = "available"
    row.last_probe_latency_ms = 15
    await db_session.commit()

    health = (await auth_client.get("/api/ai/health")).json()
    assert health["indexing"]["status"] == "available"
    assert health["chat"]["status"] == "available"
    assert health["embedding"]["status"] == "available"
    assert health["indexing"]["model"] == "index-model"
    assert health["chat"]["model"] == "chat-model"

    row = await db_session.get(AIProvider, provider_id)
    assert row is not None
    row.last_probe_status = "offline"
    row.last_probe_error = "connection refused"
    await db_session.commit()

    health = (await auth_client.get("/api/ai/health")).json()
    assert health["indexing"]["status"] == "unavailable"
    assert health["chat"]["status"] == "unavailable"
    assert health["embedding"]["status"] == "unavailable"
    assert "refused" in (health["indexing"]["error"] or "").lower()


@pytest.mark.asyncio
async def test_metadata_suggestion_soft_skips_on_ai_error(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _enable_auto_tagging(auth_client, db_session)
    monkeypatch.setattr(
        "lesspaper_ngl.workers.processor.get_adapter",
        lambda _provider, api_key=None: _FailingAdapter(),
    )

    response = await auth_client.post(
        "/api/documents/upload",
        files={
            "file": (
                "policy.txt",
                b"Insurance renewal notice with enough text for AI filing suggestions.\n",
                "text/plain",
            )
        },
    )
    assert response.status_code == 201, response.text
    doc_id = uuid.UUID(response.json()["id"])

    extract_job = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == doc_id,
                Job.job_type == JobType.TEXT_EXTRACTION,
            )
        )
    ).scalar_one()
    extract_job.status = JobStatus.RUNNING
    await process_text_extraction(db_session, extract_job)
    extract_job.status = JobStatus.COMPLETED
    await db_session.commit()

    suggest_job = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == doc_id,
                Job.job_type == JobType.METADATA_SUGGESTION,
            )
        )
    ).scalar_one()
    suggest_job.status = JobStatus.RUNNING
    result = await process_metadata_suggestion(db_session, suggest_job)
    suggest_job.status = JobStatus.COMPLETED
    await db_session.commit()

    assert result.get("skipped") is True
    assert result.get("reason") == "ai_unavailable"

    doc = await db_session.get(Document, doc_id)
    assert doc is not None
    assert doc.processing_status == ProcessingStatus.READY
    assert doc.processing_error is None

    detail = await auth_client.get(f"/api/documents/{doc_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["processing_status"] == "ready"
    assert body["inbox_status"] != "failed"
