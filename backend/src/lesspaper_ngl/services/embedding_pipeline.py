"""Bounded, resumable document embedding pipeline."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.assignments import resolve_assignment
from lesspaper_ngl.ai.base import AIProviderError
from lesspaper_ngl.ai.embeddings import pad_embedding
from lesspaper_ngl.ai.privacy import PrivacyGate
from lesspaper_ngl.ai.registry import get_adapter
from lesspaper_ngl.ai.retry import (
    ADAPTER_RETRY_ATTEMPTS,
    adapter_retry_delay_seconds,
    is_non_retryable_ai_error,
    is_oversized_input_error,
    is_transient_ai_error,
)
from lesspaper_ngl.ai.usage import record_usage
from lesspaper_ngl.bootstrap import ensure_ai_settings
from lesspaper_ngl.core.logging import get_logger
from lesspaper_ngl.models import (
    AIWorkloadRole,
    ChunkEmbeddingStatus,
    Document,
    DocumentChunk,
    Job,
    JobStatus,
    JobType,
    ProcessingStatus,
)
from lesspaper_ngl.services import jobs as job_service
from lesspaper_ngl.services.chunking import estimate_tokens, split_oversized_text
from lesspaper_ngl.services.embedding_capabilities import (
    MAX_CHUNK_EMBED_ATTEMPTS,
    MAX_ISOLATION_DEPTH,
    EmbeddingCapabilities,
    resolve_embedding_capabilities,
)
from lesspaper_ngl.services.quotas import assert_ai_quota

logger = get_logger(__name__)


@dataclass(slots=True)
class EmbeddingRunResult:
    embedded: int = 0
    failed: int = 0
    pending: int = 0
    batches: int = 0
    resumed: bool = False
    cancelled: bool = False
    continued: bool = False
    skipped: bool = False
    reason: str | None = None
    dimension: int | None = None

    def as_dict(self) -> dict:
        payload = {
            "embedded": self.embedded,
            "failed": self.failed,
            "pending": self.pending,
            "batches": self.batches,
            "resumed": self.resumed,
            "cancelled": self.cancelled,
            "continued": self.continued,
        }
        if self.skipped:
            payload["skipped"] = True
            if self.reason:
                payload["reason"] = self.reason
        if self.dimension is not None:
            payload["dimension"] = self.dimension
        return payload


async def process_document_embeddings(
    session: AsyncSession,
    job: Job,
) -> dict:
    """Embed pending chunks in bounded batches with resume and isolation."""
    if job.document_id is None:
        raise ValueError("EMBEDDING job requires document_id")

    doc = await session.get(Document, job.document_id)
    if doc is None:
        raise ValueError(f"Document {job.document_id} not found")

    ai_settings = await ensure_ai_settings(session)
    embedding = await resolve_assignment(session, AIWorkloadRole.EMBEDDING)
    if embedding.provider is None or not embedding.model:
        return EmbeddingRunResult(skipped=True, reason="no_embedding_provider").as_dict()

    provider = embedding.provider
    if not provider.enabled:
        return EmbeddingRunResult(skipped=True, reason="provider_unavailable").as_dict()
    if provider.last_probe_status != "available":
        return EmbeddingRunResult(skipped=True, reason="provider_unavailable").as_dict()

    PrivacyGate(ai_settings, provider).assert_can_embed()
    await assert_ai_quota(session, doc.owner_id)

    caps = resolve_embedding_capabilities(provider)
    model = embedding.model
    adapter = get_adapter(provider)

    # Snapshot progress before this run (for resume reporting).
    counts_before = await _count_statuses(session, doc.id)
    resumed = counts_before.get(ChunkEmbeddingStatus.EMBEDDED, 0) > 0

    if doc.embedding_started_at is None:
        doc.embedding_started_at = datetime.now(UTC)
    doc.embedding_error = None
    await _refresh_document_progress(session, doc)
    await session.flush()

    result = EmbeddingRunResult(resumed=resumed)
    started = time.perf_counter()
    total_input_tokens = 0
    last_dimension: int | None = None

    try:
        while True:
            if await _job_cancelled(session, job.id):
                result.cancelled = True
                logger.info(
                    "Embedding cancelled document_id=%s embedded=%s pending=%s",
                    doc.id,
                    result.embedded,
                    result.pending,
                )
                break

            if (
                result.batches >= caps.job_batch_budget
                or (time.perf_counter() - started) >= caps.job_time_budget_seconds
            ):
                pending = await _count_pending(session, doc.id)
                if pending > 0:
                    await job_service.enqueue_job(
                        session,
                        job_type=JobType.EMBEDDING,
                        document_id=doc.id,
                        priority=job.priority,
                    )
                    result.continued = True
                    result.pending = pending
                    logger.info(
                        "Embedding continuation enqueued document_id=%s pending=%s batches=%s",
                        doc.id,
                        pending,
                        result.batches,
                    )
                break

            batch = await _load_pending_batch(session, doc.id, caps.batch_size)
            if not batch:
                break

            # Ensure no chunk exceeds provider max before sending.
            batch = await _ensure_token_safe(session, doc, batch, caps)
            if not batch:
                continue

            await job_service.touch_job_lock(session, job.id)
            await session.flush()

            batch_result = await _embed_batch_with_isolation(
                session,
                doc=doc,
                chunks=batch,
                adapter=adapter,
                provider_name=provider.name,
                model=model,
                caps=caps,
                depth=0,
            )
            result.batches += 1
            result.embedded += batch_result.embedded
            result.failed += batch_result.failed
            total_input_tokens += batch_result.input_tokens
            if batch_result.dimension is not None:
                last_dimension = batch_result.dimension

            await _refresh_document_progress(session, doc)
            # Commit so crash recovery keeps completed batches.
            await session.commit()
            # Re-attach document after commit for subsequent updates.
            doc = await session.get(Document, job.document_id)
            assert doc is not None

        counts = await _count_statuses(session, doc.id)
        embedded_count = counts.get(ChunkEmbeddingStatus.EMBEDDED, 0)
        failed_count = counts.get(ChunkEmbeddingStatus.FAILED, 0)
        pending_count = counts.get(ChunkEmbeddingStatus.PENDING, 0) + counts.get(
            ChunkEmbeddingStatus.EMBEDDING, 0
        )
        result.pending = pending_count
        result.dimension = last_dimension

        await _finalize_document(
            session,
            doc,
            embedded=embedded_count,
            failed=failed_count,
            pending=pending_count,
            cancelled=result.cancelled,
            continued=result.continued,
            provider_name=provider.name,
            model=model,
            dimension=last_dimension,
            ai_settings=ai_settings,
        )

        duration_ms = round((time.perf_counter() - started) * 1000)
        if result.embedded > 0:
            await record_usage(
                session,
                user_id=doc.owner_id,
                provider=provider.name,
                model=model,
                operation="embedding",
                input_tokens=total_input_tokens or None,
                is_local=provider.is_local,
                document_id=doc.id,
                duration_ms=duration_ms,
            )

        logger.info(
            "Embedding finished document_id=%s embedded=%s failed=%s pending=%s "
            "batches=%s resumed=%s cancelled=%s continued=%s duration_ms=%s "
            "provider=%s model=%s batch_size=%s",
            doc.id,
            embedded_count,
            failed_count,
            pending_count,
            result.batches,
            result.resumed,
            result.cancelled,
            result.continued,
            duration_ms,
            provider.name,
            model,
            caps.batch_size,
        )
        return result.as_dict()
    finally:
        await adapter.aclose()


@dataclass(slots=True)
class _BatchOutcome:
    embedded: int = 0
    failed: int = 0
    input_tokens: int = 0
    dimension: int | None = None


async def _embed_batch_with_isolation(
    session: AsyncSession,
    *,
    doc: Document,
    chunks: list[DocumentChunk],
    adapter,
    provider_name: str,
    model: str,
    caps: EmbeddingCapabilities,
    depth: int,
) -> _BatchOutcome:
    if not chunks:
        return _BatchOutcome()

    chunk_ids = [c.id for c in chunks]
    await session.execute(
        update(DocumentChunk)
        .where(DocumentChunk.id.in_(chunk_ids))
        .values(embedding_status=ChunkEmbeddingStatus.EMBEDDING)
    )
    await session.flush()

    texts = [c.text for c in chunks]
    try:
        # Space identity uses the assigned/requested model ID, not the provider
        # response echo (e.g. OpenRouter may return an unprefixed name).
        vectors, input_tokens, _used_model = await _call_embed_with_retries(
            adapter, texts, model=model
        )
    except AIProviderError as exc:
        if is_oversized_input_error(exc) and len(chunks) == 1:
            return await _split_single_chunk(
                session,
                doc=doc,
                chunk=chunks[0],
                caps=caps,
                error=str(exc),
            )
        if (is_oversized_input_error(exc) or is_transient_ai_error(exc)) and len(chunks) > 1:
            if depth >= MAX_ISOLATION_DEPTH:
                return await _mark_chunks_failed(session, chunks, str(exc))
            mid = len(chunks) // 2
            left = await _embed_batch_with_isolation(
                session,
                doc=doc,
                chunks=chunks[:mid],
                adapter=adapter,
                provider_name=provider_name,
                model=model,
                caps=caps,
                depth=depth + 1,
            )
            right = await _embed_batch_with_isolation(
                session,
                doc=doc,
                chunks=chunks[mid:],
                adapter=adapter,
                provider_name=provider_name,
                model=model,
                caps=caps,
                depth=depth + 1,
            )
            return _BatchOutcome(
                embedded=left.embedded + right.embedded,
                failed=left.failed + right.failed,
                input_tokens=left.input_tokens + right.input_tokens,
                dimension=left.dimension or right.dimension,
            )
        if is_non_retryable_ai_error(exc) and len(chunks) > 1 and depth < MAX_ISOLATION_DEPTH:
            # Isolate to find the bad apple; config errors on whole batch still fail all.
            mid = len(chunks) // 2
            left = await _embed_batch_with_isolation(
                session,
                doc=doc,
                chunks=chunks[:mid],
                adapter=adapter,
                provider_name=provider_name,
                model=model,
                caps=caps,
                depth=depth + 1,
            )
            right = await _embed_batch_with_isolation(
                session,
                doc=doc,
                chunks=chunks[mid:],
                adapter=adapter,
                provider_name=provider_name,
                model=model,
                caps=caps,
                depth=depth + 1,
            )
            return _BatchOutcome(
                embedded=left.embedded + right.embedded,
                failed=left.failed + right.failed,
                input_tokens=left.input_tokens + right.input_tokens,
                dimension=left.dimension or right.dimension,
            )
        force_failed = is_non_retryable_ai_error(exc) or (
            not is_transient_ai_error(exc) and not is_oversized_input_error(exc)
        )
        return await _mark_chunks_failed(
            session, chunks, _safe_error_message(exc), force_failed=force_failed
        )

    if len(vectors) != len(chunks):
        return await _mark_chunks_failed(session, chunks, "Embedding count mismatch")

    dimension = len(vectors[0]) if vectors else None
    for chunk, vector in zip(chunks, vectors, strict=True):
        chunk.embedding = pad_embedding(vector)
        chunk.embedding_provider = provider_name
        chunk.embedding_model = model
        chunk.embedding_dimension = dimension
        chunk.embedding_status = ChunkEmbeddingStatus.EMBEDDED
        chunk.embedding_error = None
        chunk.embedding_attempts = (chunk.embedding_attempts or 0) + 1
    await session.flush()
    return _BatchOutcome(
        embedded=len(chunks),
        failed=0,
        input_tokens=input_tokens or 0,
        dimension=dimension,
    )


async def _call_embed_with_retries(adapter, texts: list[str], *, model: str):
    last_exc: AIProviderError | None = None
    for attempt in range(1, ADAPTER_RETRY_ATTEMPTS + 1):
        try:
            result = await adapter.embed(texts, model=model)
            return result.embeddings, result.input_tokens, result.model
        except AIProviderError as exc:
            last_exc = exc
            if is_oversized_input_error(exc) or is_non_retryable_ai_error(exc):
                raise
            if not is_transient_ai_error(exc) or attempt >= ADAPTER_RETRY_ATTEMPTS:
                raise
            await asyncio.sleep(adapter_retry_delay_seconds(attempt))
    assert last_exc is not None
    raise last_exc


async def _split_single_chunk(
    session: AsyncSession,
    *,
    doc: Document,
    chunk: DocumentChunk,
    caps: EmbeddingCapabilities,
    error: str,
) -> _BatchOutcome:
    """Replace an oversized chunk with smaller siblings and leave them pending."""
    max_tokens = min(caps.recommended_chunk_tokens, caps.max_input_tokens)
    # Split more aggressively than the failed size.
    safer_max = max(64, max_tokens // 2) if estimate_tokens(chunk.text) > max_tokens else max(
        64, estimate_tokens(chunk.text) // 2
    )
    safer_max = max(32, min(safer_max, max_tokens))

    drafts = split_oversized_text(
        chunk.text,
        max_tokens=safer_max,
        page_number=chunk.page_number,
        page_end=chunk.page_end,
        section=chunk.section,
        start_index=chunk.chunk_index,
    )
    if len(drafts) <= 1:
        chunk.embedding_status = ChunkEmbeddingStatus.FAILED
        chunk.embedding_error = _truncate_error(error)
        chunk.embedding_attempts = (chunk.embedding_attempts or 0) + 1
        await session.flush()
        return _BatchOutcome(failed=1)

    # Shift subsequent chunk indexes to make room (descending to avoid clashes).
    extra = len(drafts) - 1
    later = (
        await session.execute(
            select(DocumentChunk)
            .where(
                DocumentChunk.document_id == doc.id,
                DocumentChunk.chunk_index > chunk.chunk_index,
            )
            .order_by(DocumentChunk.chunk_index.desc())
        )
    ).scalars().all()
    for later_chunk in later:
        later_chunk.chunk_index += extra
    await session.flush()

    first, *rest = drafts
    chunk.text = first.text
    chunk.token_count = first.token_count
    chunk.content_hash = first.content_hash
    chunk.page_number = first.page_number
    chunk.page_end = first.page_end
    chunk.embedding_status = ChunkEmbeddingStatus.PENDING
    chunk.embedding_error = None
    chunk.embedding = None
    chunk.embedding_provider = None
    chunk.embedding_model = None
    chunk.embedding_dimension = None
    chunk.embedding_attempts = (chunk.embedding_attempts or 0) + 1

    for offset, draft in enumerate(rest, start=1):
        session.add(
            DocumentChunk(
                document_id=doc.id,
                page_number=draft.page_number,
                page_end=draft.page_end,
                section=draft.section,
                chunk_index=chunk.chunk_index + offset,
                text=draft.text,
                token_count=draft.token_count,
                content_hash=draft.content_hash,
                chunking_version=chunk.chunking_version,
                embedding_status=ChunkEmbeddingStatus.PENDING,
            )
        )
    await _refresh_document_progress(session, doc)
    await session.flush()
    logger.info(
        "Split oversized chunk document_id=%s chunk_index=%s into %s parts",
        doc.id,
        chunk.chunk_index,
        len(drafts),
    )
    return _BatchOutcome()


async def _mark_chunks_failed(
    session: AsyncSession,
    chunks: list[DocumentChunk],
    error: str,
    *,
    force_failed: bool = False,
) -> _BatchOutcome:
    msg = _truncate_error(error)
    for chunk in chunks:
        attempts = (chunk.embedding_attempts or 0) + 1
        chunk.embedding_attempts = attempts
        if force_failed or attempts >= MAX_CHUNK_EMBED_ATTEMPTS:
            chunk.embedding_status = ChunkEmbeddingStatus.FAILED
            chunk.embedding_error = msg
        else:
            # Leave pending for a later continuation / job retry.
            chunk.embedding_status = ChunkEmbeddingStatus.PENDING
            chunk.embedding_error = msg
    await session.flush()
    failed = sum(
        1 for c in chunks if c.embedding_status == ChunkEmbeddingStatus.FAILED
    )
    return _BatchOutcome(failed=failed)


async def _ensure_token_safe(
    session: AsyncSession,
    doc: Document,
    chunks: list[DocumentChunk],
    caps: EmbeddingCapabilities,
) -> list[DocumentChunk]:
    """Split any loaded chunk that exceeds max_input_tokens before embedding."""
    safe: list[DocumentChunk] = []
    changed = False
    for chunk in chunks:
        if chunk.token_count <= caps.max_input_tokens and estimate_tokens(chunk.text) <= caps.max_input_tokens:
            safe.append(chunk)
            continue
        changed = True
        await _split_single_chunk(
            session,
            doc=doc,
            chunk=chunk,
            caps=caps,
            error="Chunk exceeded provider max input tokens",
        )
    if changed:
        # Reload a fresh pending batch after splits.
        return await _load_pending_batch(session, doc.id, caps.batch_size)
    return safe


async def _load_pending_batch(
    session: AsyncSession,
    document_id: uuid.UUID,
    batch_size: int,
) -> list[DocumentChunk]:
    result = await session.execute(
        select(DocumentChunk)
        .where(
            DocumentChunk.document_id == document_id,
            DocumentChunk.embedding_status.in_(
                [ChunkEmbeddingStatus.PENDING, ChunkEmbeddingStatus.EMBEDDING]
            ),
        )
        .order_by(DocumentChunk.chunk_index)
        .limit(batch_size)
    )
    return list(result.scalars().all())


async def _count_statuses(
    session: AsyncSession, document_id: uuid.UUID
) -> dict[ChunkEmbeddingStatus, int]:
    rows = (
        await session.execute(
            select(DocumentChunk.embedding_status, func.count())
            .where(DocumentChunk.document_id == document_id)
            .group_by(DocumentChunk.embedding_status)
        )
    ).all()
    return {status: int(count) for status, count in rows}


async def _count_pending(session: AsyncSession, document_id: uuid.UUID) -> int:
    counts = await _count_statuses(session, document_id)
    return counts.get(ChunkEmbeddingStatus.PENDING, 0) + counts.get(
        ChunkEmbeddingStatus.EMBEDDING, 0
    )


async def _refresh_document_progress(session: AsyncSession, doc: Document) -> None:
    counts = await _count_statuses(session, doc.id)
    total = sum(counts.values())
    doc.chunks_total = total
    doc.chunks_embedded = counts.get(ChunkEmbeddingStatus.EMBEDDED, 0)
    doc.chunks_failed = counts.get(ChunkEmbeddingStatus.FAILED, 0)


async def _finalize_document(
    session: AsyncSession,
    doc: Document,
    *,
    embedded: int,
    failed: int,
    pending: int,
    cancelled: bool,
    continued: bool,
    provider_name: str,
    model: str,
    dimension: int | None,
    ai_settings,
) -> None:
    await _refresh_document_progress(session, doc)

    if cancelled:
        doc.embedding_error = "Embedding cancelled; completed vectors were preserved"
        await session.flush()
        return

    if continued:
        doc.embedding_error = None
        await session.flush()
        return

    if pending > 0 and failed == 0:
        # Unexpected leftover pending without continuation — leave for retry.
        doc.embedding_error = "Embedding paused; processing can be resumed"
        doc.has_embeddings = False
        await session.flush()
        return

    if failed > 0 and embedded > 0:
        doc.has_embeddings = True  # usable partial semantic search
        doc.processing_status = ProcessingStatus.PARTIAL
        doc.embedding_error = f"{failed} of {embedded + failed + pending} chunks could not be embedded"
        doc.embedding_finished_at = datetime.now(UTC)
    elif failed > 0 and embedded == 0:
        doc.has_embeddings = False
        doc.embedding_error = f"{failed} chunks could not be embedded"
        doc.embedding_finished_at = datetime.now(UTC)
        if doc.processing_status != ProcessingStatus.FAILED:
            doc.processing_status = ProcessingStatus.PARTIAL
    elif embedded > 0:
        doc.has_embeddings = True
        doc.embedding_error = None
        doc.embedding_finished_at = datetime.now(UTC)
        if doc.processing_status == ProcessingStatus.PARTIAL or doc.processing_status != ProcessingStatus.FAILED:
            doc.processing_status = ProcessingStatus.READY
        ai_settings.active_embedding_provider = provider_name
        ai_settings.active_embedding_model = model
        ai_settings.active_embedding_dimension = dimension
    else:
        doc.has_embeddings = False

    await session.flush()


async def _job_cancelled(session: AsyncSession, job_id: uuid.UUID) -> bool:
    status = (
        await session.execute(select(Job.status).where(Job.id == job_id))
    ).scalar_one_or_none()
    return status == JobStatus.CANCELLED


def _safe_error_message(exc: BaseException) -> str:
    if isinstance(exc, AIProviderError):
        return _truncate_error(exc.message)
    return _truncate_error(str(exc))


def _truncate_error(message: str, limit: int = 400) -> str:
    text = " ".join(message.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def iter_batches(items: list, batch_size: int) -> list[list]:
    """Split ``items`` into contiguous batches (pure helper for tests)."""
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if not items:
        return []
    return [items[i : i + batch_size] for i in range(0, len(items), batch_size)]


async def reset_chunk_embeddings(session: AsyncSession, document_id: uuid.UUID) -> int:
    """Clear vectors and reset chunk embedding status for re-embed."""
    result = await session.execute(
        update(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .values(
            embedding=None,
            embedding_provider=None,
            embedding_model=None,
            embedding_dimension=None,
            embedding_status=ChunkEmbeddingStatus.PENDING,
            embedding_error=None,
            embedding_attempts=0,
        )
    )
    return result.rowcount or 0
