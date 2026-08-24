"""Reprocess embeddings and metadata suggestions."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.embeddings import pad_embedding
from lesspaper_ngl.models import Document, DocumentChunk, Job, JobStatus, JobType


async def _assign_ai_models(auth_client: AsyncClient) -> str:
    provider = await auth_client.post(
        "/api/ai/providers",
        json={
            "name": "reprocess-provider",
            "kind": "openai_compatible",
            "base_url": "http://127.0.0.1:9/v1",
            "is_local": True,
            "chat_model": "chat-model",
            "embedding_model": "embed-model",
            "supports_embeddings": True,
        },
    )
    assert provider.status_code == 201, provider.text
    provider_id = provider.json()["id"]

    for role, model in (
        ("indexing", "chat-model"),
        ("embedding", "embed-model"),
    ):
        response = await auth_client.patch(
            "/api/ai/assignments",
            json={"role": role, "provider_id": provider_id, "model": model},
        )
        assert response.status_code == 200, response.text
    return provider_id


@pytest.mark.asyncio
async def test_reprocess_embeddings_enqueues_job(
    auth_client: AsyncClient,
    uploaded_txt_doc: dict,
    db_session: AsyncSession,
) -> None:
    await _assign_ai_models(auth_client)
    doc_id = uuid.UUID(uploaded_txt_doc["id"])

    chunks = (
        await db_session.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc_id))
    ).scalars().all()
    assert chunks
    for chunk in chunks:
        chunk.embedding = pad_embedding([0.1] * 8)
        chunk.embedding_model = "old-model"
        chunk.embedding_dimension = 8
    document = await db_session.get(Document, doc_id)
    assert document is not None
    document.has_embeddings = True
    await db_session.commit()

    response = await auth_client.post(f"/api/documents/{doc_id}/reprocess-embeddings")
    assert response.status_code == 200, response.text
    assert response.json()["has_embeddings"] is False

    await db_session.refresh(chunks[0])
    assert chunks[0].embedding is None

    job = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == doc_id,
                Job.job_type == JobType.EMBEDDING,
                Job.status == JobStatus.QUEUED,
            )
        )
    ).scalar_one()
    assert job.retry_count == 0


@pytest.mark.asyncio
async def test_reprocess_suggestions_enqueues_manual_job(
    auth_client: AsyncClient,
    uploaded_txt_doc: dict,
    db_session: AsyncSession,
) -> None:
    await _assign_ai_models(auth_client)
    doc_id = uuid.UUID(uploaded_txt_doc["id"])

    response = await auth_client.post(f"/api/documents/{doc_id}/reprocess-suggestions")
    assert response.status_code == 200, response.text

    job = (
        await db_session.execute(
            select(Job).where(
                Job.document_id == doc_id,
                Job.job_type == JobType.METADATA_SUGGESTION,
                Job.status == JobStatus.QUEUED,
            )
        )
    ).scalar_one()
    assert job.payload.get("manual") is True


@pytest.mark.asyncio
async def test_reprocess_embeddings_requires_index(
    auth_client: AsyncClient,
    sample_txt_path,
) -> None:
    await _assign_ai_models(auth_client)
    with sample_txt_path.open("rb") as fh:
        uploaded = await auth_client.post(
            "/api/documents/upload",
            files={"file": ("no-index.txt", fh, "text/plain")},
        )
    assert uploaded.status_code == 201
    doc_id = uploaded.json()["id"]

    response = await auth_client.post(f"/api/documents/{doc_id}/reprocess-embeddings")
    assert response.status_code == 422
    assert "indexed" in response.json()["message"].lower()
