"""Integration tests for resumable batched embeddings."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.base import EmbeddingResult
from lesspaper_ngl.ai.embeddings import pad_embedding
from lesspaper_ngl.models import (
    ChunkEmbeddingStatus,
    Document,
    DocumentChunk,
    JobStatus,
    JobType,
)
from lesspaper_ngl.services.embedding_pipeline import process_document_embeddings
from lesspaper_ngl.services.jobs import enqueue_job


def _make_chunk(
    document_id: uuid.UUID,
    index: int,
    *,
    status: ChunkEmbeddingStatus = ChunkEmbeddingStatus.PENDING,
    text: str | None = None,
) -> DocumentChunk:
    return DocumentChunk(
        document_id=document_id,
        chunk_index=index,
        page_number=1,
        page_end=1,
        text=text or f"Chunk text number {index} with enough content for embedding.",
        token_count=12,
        content_hash=f"hash-{index}",
        embedding_status=status,
    )


@pytest.mark.asyncio
async def test_embedding_resume_skips_completed_chunks(
    uploaded_txt_doc: dict,
    db_session: AsyncSession,
) -> None:
    doc_id = uuid.UUID(uploaded_txt_doc["id"])
    doc = await db_session.get(Document, doc_id)
    assert doc is not None

    # Replace with a controlled chunk set.
    existing = (
        await db_session.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc_id))
    ).scalars().all()
    for chunk in existing:
        await db_session.delete(chunk)
    await db_session.flush()

    total = 40
    for i in range(total):
        chunk = _make_chunk(doc_id, i)
        if i < 10:
            chunk.embedding = pad_embedding([0.01 * i] * 8)
            chunk.embedding_status = ChunkEmbeddingStatus.EMBEDDED
            chunk.embedding_provider = "test"
            chunk.embedding_model = "embed-model"
            chunk.embedding_dimension = 8
        db_session.add(chunk)

    doc.document_indexed = True
    doc.has_embeddings = False
    doc.chunks_total = total
    doc.chunks_embedded = 10
    doc.chunks_failed = 0
    await db_session.flush()

    job = await enqueue_job(
        db_session,
        job_type=JobType.EMBEDDING,
        document_id=doc_id,
        priority=10,
    )
    job.status = JobStatus.RUNNING
    await db_session.commit()

    provider = SimpleNamespace(
        name="test-provider",
        enabled=True,
        is_local=True,
        last_probe_status="available",
        embedding_model="embed-model",
        embedding_max_input_tokens=8192,
        embedding_recommended_chunk_tokens=512,
        embedding_batch_size=8,
        embedding_max_batch_size=32,
        embedding_concurrency=1,
        kind=SimpleNamespace(value="openai_compatible"),
        base_url="http://127.0.0.1:9/v1",
    )
    assignment = SimpleNamespace(provider=provider, model="embed-model")

    call_sizes: list[int] = []

    async def fake_embed(texts: list[str], *, model: str | None = None) -> EmbeddingResult:
        call_sizes.append(len(texts))
        return EmbeddingResult(
            embeddings=[[0.1] * 8 for _ in texts],
            model=model or "embed-model",
            input_tokens=len(texts) * 12,
        )

    adapter = MagicMock()
    adapter.embed = AsyncMock(side_effect=fake_embed)
    adapter.aclose = AsyncMock()

    with (
        patch(
            "lesspaper_ngl.services.embedding_pipeline.resolve_assignment",
            AsyncMock(return_value=assignment),
        ),
        patch(
            "lesspaper_ngl.services.embedding_pipeline.ensure_ai_settings",
            AsyncMock(return_value=SimpleNamespace(
                active_embedding_provider=None,
                active_embedding_model=None,
                active_embedding_dimension=None,
                allow_remote_embeddings=True,
                privacy_mode=SimpleNamespace(value="standard"),
                block_remote_ai=False,
            )),
        ),
        patch("lesspaper_ngl.services.embedding_pipeline.PrivacyGate") as privacy_cls,
        patch("lesspaper_ngl.services.embedding_pipeline.assert_ai_quota", AsyncMock()),
        patch("lesspaper_ngl.services.embedding_pipeline.get_adapter", return_value=adapter),
        patch("lesspaper_ngl.services.embedding_pipeline.record_usage", AsyncMock()),
    ):
        privacy_cls.return_value.assert_can_embed = MagicMock()
        result = await process_document_embeddings(db_session, job)

    assert result["resumed"] is True
    assert result["embedded"] == 30
    # Provider must never see the already-embedded first 10.
    assert sum(call_sizes) == 30
    assert max(call_sizes) <= 8

    await db_session.refresh(doc)
    assert doc.has_embeddings is True
    assert doc.chunks_embedded == 40
    assert doc.chunks_failed == 0

    statuses = (
        await db_session.execute(
            select(DocumentChunk.embedding_status).where(DocumentChunk.document_id == doc_id)
        )
    ).scalars().all()
    assert all(s == ChunkEmbeddingStatus.EMBEDDED for s in statuses)


@pytest.mark.asyncio
async def test_embedding_idempotent_re_run(
    uploaded_txt_doc: dict,
    db_session: AsyncSession,
) -> None:
    doc_id = uuid.UUID(uploaded_txt_doc["id"])
    # Ensure at least one pending chunk exists from the fixture pipeline.
    chunks = (
        await db_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc_id).order_by(DocumentChunk.chunk_index)
        )
    ).scalars().all()
    if not chunks:
        db_session.add(_make_chunk(doc_id, 0))
        await db_session.flush()
        chunks = (
            await db_session.execute(select(DocumentChunk).where(DocumentChunk.document_id == doc_id))
        ).scalars().all()

    for chunk in chunks:
        chunk.embedding_status = ChunkEmbeddingStatus.PENDING
        chunk.embedding = None

    doc = await db_session.get(Document, doc_id)
    assert doc is not None
    doc.document_indexed = True
    doc.has_embeddings = False
    doc.chunks_total = len(chunks)
    doc.chunks_embedded = 0

    job = await enqueue_job(db_session, job_type=JobType.EMBEDDING, document_id=doc_id)
    job.status = JobStatus.RUNNING
    await db_session.commit()

    provider = SimpleNamespace(
        name="idem-provider",
        enabled=True,
        is_local=True,
        last_probe_status="available",
        embedding_model="embed-model",
        embedding_max_input_tokens=8192,
        embedding_recommended_chunk_tokens=512,
        embedding_batch_size=16,
        embedding_max_batch_size=32,
        embedding_concurrency=1,
        kind=SimpleNamespace(value="openai_compatible"),
        base_url="http://127.0.0.1:9/v1",
    )
    assignment = SimpleNamespace(provider=provider, model="embed-model")
    adapter = MagicMock()
    adapter.embed = AsyncMock(
        side_effect=lambda texts, model=None: EmbeddingResult(
            embeddings=[[0.2] * 8 for _ in texts],
            model=model or "embed-model",
            input_tokens=len(texts),
        )
    )
    adapter.aclose = AsyncMock()

    with (
        patch(
            "lesspaper_ngl.services.embedding_pipeline.resolve_assignment",
            AsyncMock(return_value=assignment),
        ),
        patch(
            "lesspaper_ngl.services.embedding_pipeline.ensure_ai_settings",
            AsyncMock(
                return_value=SimpleNamespace(
                    active_embedding_provider=None,
                    active_embedding_model=None,
                    active_embedding_dimension=None,
                    allow_remote_embeddings=True,
                    privacy_mode=SimpleNamespace(value="standard"),
                    block_remote_ai=False,
                )
            ),
        ),
        patch("lesspaper_ngl.services.embedding_pipeline.PrivacyGate") as privacy_cls,
        patch("lesspaper_ngl.services.embedding_pipeline.assert_ai_quota", AsyncMock()),
        patch("lesspaper_ngl.services.embedding_pipeline.get_adapter", return_value=adapter),
        patch("lesspaper_ngl.services.embedding_pipeline.record_usage", AsyncMock()),
    ):
        privacy_cls.return_value.assert_can_embed = MagicMock()
        first = await process_document_embeddings(db_session, job)
        job2 = await enqueue_job(db_session, job_type=JobType.EMBEDDING, document_id=doc_id)
        job2.status = JobStatus.RUNNING
        await db_session.flush()
        second = await process_document_embeddings(db_session, job2)

    assert first["embedded"] == len(chunks)
    assert second["embedded"] == 0
    assert adapter.embed.await_count >= 1

    count = (
        await db_session.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc_id)
        )
    ).scalars().all()
    assert len(count) == len(chunks)
    assert all(c.embedding is not None for c in count)
