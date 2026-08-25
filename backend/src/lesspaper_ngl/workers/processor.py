"""Background job processing."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import UTC, datetime
from functools import partial

import pymupdf
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.assignments import resolve_assignment
from lesspaper_ngl.ai.base import AIProviderError, ChatMessage
from lesspaper_ngl.ai.busy import provider_chat_guard
from lesspaper_ngl.ai.filing_context import (
    PageText,
    build_filing_sample,
    format_filing_document_block,
    legacy_prefix_fallback,
    rank_folder_candidates,
    rank_tag_candidates,
    tokenize_for_candidates,
)
from lesspaper_ngl.ai.privacy import PrivacyGate
from lesspaper_ngl.ai.registry import get_adapter
from lesspaper_ngl.ai.retry import is_transient_ai_error
from lesspaper_ngl.ai.usage import record_usage
from lesspaper_ngl.bootstrap import ensure_ai_settings
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.exceptions import PrivacyViolationError, ValidationError
from lesspaper_ngl.core.logging import get_logger
from lesspaper_ngl.db.session import session_scope
from lesspaper_ngl.models import (
    AISuggestion,
    AIWorkloadRole,
    ChunkEmbeddingStatus,
    Correspondent,
    Document,
    DocumentChunk,
    DocumentPage,
    DocumentTag,
    DocumentType,
    Folder,
    FolderKind,
    Job,
    JobStatus,
    JobType,
    ProcessingStatus,
    SuggestionStatus,
    Tag,
)
from lesspaper_ngl.ocr.extractor import (
    ExtractedPage,
    detect_language_hint,
    extract_document,
    pages_need_ocr,
)
from lesspaper_ngl.ocr.previews import persist_previews
from lesspaper_ngl.search.fts import (
    refresh_document_search_vector,
    refresh_page_search_vectors,
)
from lesspaper_ngl.services import jobs as job_service
from lesspaper_ngl.services import library_stats
from lesspaper_ngl.services.chunking import PageInput, chunk_pages
from lesspaper_ngl.services.documents import invalidate_retrieval_artifacts
from lesspaper_ngl.services.embedding_capabilities import resolve_embedding_capabilities
from lesspaper_ngl.services.embedding_pipeline import process_document_embeddings
from lesspaper_ngl.services.quotas import assert_ai_quota
from lesspaper_ngl.storage.service import StorageService
from lesspaper_ngl.workers.ocr_gate import ocr_exclusive_section

logger = get_logger(__name__)

# Align with metadata-suggestion minimum; below this, scanned PDFs need OCR first.
_MIN_TEXT_FOR_AI = 20

PREFLIGHT_JOB_TYPES = frozenset(
    {
        JobType.TEXT_EXTRACTION,
        JobType.OCR,
        JobType.METADATA_SUGGESTION,
    }
)

# AI enrichment is optional: terminal failures must not fail the document.
SOFT_FAIL_PREFLIGHT_JOB_TYPES = frozenset({JobType.METADATA_SUGGESTION})


async def _get_document(session: AsyncSession, document_id: uuid.UUID) -> Document:
    doc = await session.get(Document, document_id)
    if doc is None:
        raise ValueError(f"Document {document_id} not found")
    return doc


async def commit_ocr_progress(
    document_id: uuid.UUID, done: int, total: int
) -> None:
    """Commit page progress on a separate session so the UI can poll mid-OCR."""
    async with session_scope() as session:
        await session.execute(
            update(Document)
            .where(Document.id == document_id)
            .values(ocr_pages_done=done, ocr_pages_total=total)
        )


async def commit_ocr_page(
    document_id: uuid.UUID, page_number: int, text: str
) -> None:
    """Persist one OCR page as soon as it is ready (separate session)."""
    async with session_scope() as session:
        session.add(
            DocumentPage(
                document_id=document_id,
                page_number=page_number,
                text=text,
            )
        )


async def clear_document_pages(document_id: uuid.UUID) -> None:
    """Delete all pages for a document and commit (required before streamed inserts)."""
    async with session_scope() as session:
        await session.execute(
            delete(DocumentPage).where(DocumentPage.document_id == document_id)
        )


def _ocr_progress_callback(loop: asyncio.AbstractEventLoop, document_id: uuid.UUID):
    def _on_progress(done: int, total: int) -> None:
        try:
            fut = asyncio.run_coroutine_threadsafe(
                commit_ocr_progress(document_id, done, total),
                loop,
            )
            fut.result(timeout=15)
        except Exception:
            logger.debug(
                "OCR progress update failed for doc=%s", document_id, exc_info=True
            )

    return _on_progress


def _ocr_page_callback(
    loop: asyncio.AbstractEventLoop,
    document_id: uuid.UUID,
    full_text_parts: list[str],
):
    def _on_page(page_number: int, text: str) -> None:
        try:
            fut = asyncio.run_coroutine_threadsafe(
                commit_ocr_page(document_id, page_number, text),
                loop,
            )
            fut.result(timeout=30)
        except Exception:
            logger.exception(
                "OCR page persist failed for doc=%s page=%s",
                document_id,
                page_number,
            )
            raise
        if text.strip():
            full_text_parts.append(text)

    return _on_page


async def _has_open_preflight_jobs(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    exclude_job_id: uuid.UUID | None = None,
) -> bool:
    stmt = select(Job.id).where(
        Job.document_id == document_id,
        Job.job_type.in_(PREFLIGHT_JOB_TYPES),
        Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
    )
    if exclude_job_id is not None:
        stmt = stmt.where(Job.id != exclude_job_id)
    return (await session.execute(stmt.limit(1))).scalar_one_or_none() is not None


async def _has_open_indexing_job(session: AsyncSession, document_id: uuid.UUID) -> bool:
    stmt = select(Job.id).where(
        Job.document_id == document_id,
        Job.job_type == JobType.INDEXING,
        Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
    )
    return (await session.execute(stmt.limit(1))).scalar_one_or_none() is not None


async def _enqueue_library_indexing(
    session: AsyncSession,
    doc: Document,
    *,
    priority: int,
) -> bool:
    """Enqueue INDEXING for non-inbox library docs that are not yet indexed."""
    if doc.inbox or doc.document_indexed:
        return False
    if await _has_open_indexing_job(session, doc.id):
        return False
    await job_service.enqueue_job(
        session,
        job_type=JobType.INDEXING,
        document_id=doc.id,
        priority=priority,
    )
    return True


async def mark_preflight_ready(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    exclude_job_id: uuid.UUID | None = None,
) -> None:
    """Mark inbox/library doc ready for review when pre-flight jobs are done."""
    if await _has_open_preflight_jobs(session, document_id, exclude_job_id=exclude_job_id):
        return
    doc = await _get_document(session, document_id)
    if doc.processing_status == ProcessingStatus.FAILED:
        return
    was_ready = doc.processing_status == ProcessingStatus.READY
    doc.processing_status = ProcessingStatus.READY
    doc.processing_error = None
    await session.flush()
    # Library (non-inbox) docs: start RAG indexing after preflight.
    # Inbox docs wait for explicit Process.
    await _enqueue_library_indexing(
        session,
        doc,
        priority=100,
    )
    if not was_ready:
        await library_stats.bump_counters(
            session,
            doc.owner_id,
            successful_processing=1,
        )


async def mark_preflight_failed(session: AsyncSession, document_id: uuid.UUID, error: str) -> None:
    doc = await _get_document(session, document_id)
    was_failed = doc.processing_status == ProcessingStatus.FAILED
    doc.processing_status = ProcessingStatus.FAILED
    doc.processing_error = error[:2000]
    await session.flush()
    if not was_failed:
        await library_stats.bump_counters(
            session,
            doc.owner_id,
            failed_documents=1,
        )


def _has_usable_extracted_text(doc: Document) -> bool:
    return len((doc.extracted_text or "").strip()) >= _MIN_TEXT_FOR_AI


def _provider_reachable_for_jobs(provider) -> bool:
    """True only when a recent health probe confirmed the provider is up.

    Configured-but-offline providers must not start long AI jobs that hold DB
    transactions open (which blocks trash/metadata updates).
    """
    return bool(
        provider is not None
        and provider.enabled
        and provider.last_probe_status == "available"
    )


def _pages_from_extracted_text(text: str) -> list[ExtractedPage]:
    parts = [p.strip() for p in (text or "").split("\n\n")]
    pages = [ExtractedPage(page_number=i + 1, text=part) for i, part in enumerate(parts) if part]
    return pages or [ExtractedPage(page_number=1, text=(text or "").strip())]


def _pdf_needs_ocr_before_ai(doc: Document, *, ocr_enabled: bool) -> bool:
    """True when AI filing must wait for a dedicated OCR pass."""
    if not ocr_enabled:
        return False
    if doc.mime_type != "application/pdf":
        return False
    if doc.ocr_completed:
        return False
    return pages_need_ocr(_pages_from_extracted_text(doc.extracted_text or ""))


async def _has_open_ocr_job(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    exclude_job_id: uuid.UUID | None = None,
) -> bool:
    stmt = select(Job.id).where(
        Job.document_id == document_id,
        Job.job_type == JobType.OCR,
        Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
    )
    if exclude_job_id is not None:
        stmt = stmt.where(Job.id != exclude_job_id)
    return (await session.execute(stmt.limit(1))).scalar_one_or_none() is not None


async def _enqueue_metadata_suggestion_or_finish(
    session: AsyncSession,
    doc: Document,
    *,
    priority: int,
    exclude_job_id: uuid.UUID | None = None,
) -> None:
    # Never start AI filing while OCR is still queued/running.
    if await _has_open_ocr_job(session, doc.id, exclude_job_id=exclude_job_id):
        logger.info(
            "Deferring metadata suggestion until OCR finishes for doc=%s",
            doc.id,
        )
        return

    ai_settings = await ensure_ai_settings(session)
    indexing = await resolve_assignment(session, AIWorkloadRole.INDEXING)
    # auto_tagging is an explicit Controls off-switch, not a proxy for "no model".
    can_suggest = (
        ai_settings.auto_tagging
        and indexing.provider is not None
        and indexing.model is not None
        and _has_usable_extracted_text(doc)
    )
    if can_suggest:
        provider = indexing.provider
        if provider is not None and provider.enabled:
            # Only offer AI filing when health probe recently confirmed reachability.
            # not_configured / checking / offline → manual inbox workflow.
            if provider.last_probe_status != "available":
                logger.info(
                    "Skipping metadata suggestion; indexing provider not healthy "
                    "(probe=%s) for doc=%s",
                    provider.last_probe_status,
                    doc.id,
                )
                await mark_preflight_ready(session, doc.id, exclude_job_id=exclude_job_id)
                return
            try:
                PrivacyGate(ai_settings, provider).assert_can_qa()
            except Exception:
                can_suggest = False
            else:
                await job_service.enqueue_job(
                    session,
                    job_type=JobType.METADATA_SUGGESTION,
                    document_id=doc.id,
                    priority=priority + 20,
                )
                return
    await mark_preflight_ready(session, doc.id, exclude_job_id=exclude_job_id)


async def process_text_extraction(session: AsyncSession, job: Job) -> dict:
    if job.document_id is None:
        raise ValueError("TEXT_EXTRACTION job requires document_id")
    doc = await _get_document(session, job.document_id)
    storage = StorageService()
    path = storage.open_original_path(doc.storage_key)
    settings = get_settings()
    prior_page_count = doc.page_count or 0

    # PDFs: native text only here. OCR is a separate job so AI can wait on it.
    # Images still OCR inline (that is their only text source).
    is_pdf = doc.mime_type == "application/pdf"
    await clear_document_pages(doc.id)

    full_text_parts: list[str] = []
    loop = asyncio.get_running_loop()

    if is_pdf:
        extracted = await asyncio.to_thread(
            partial(
                extract_document,
                path,
                doc.mime_type,
                settings=settings,
                language=doc.language,
                allow_ocr=False,
            )
        )
        for page_data in extracted.pages:
            session.add(
                DocumentPage(
                    document_id=doc.id,
                    page_number=page_data.page_number,
                    text=page_data.text,
                )
            )
            if page_data.text.strip():
                full_text_parts.append(page_data.text)
    else:
        await commit_ocr_progress(doc.id, 0, 1)
        async with ocr_exclusive_section():
            extracted = await asyncio.to_thread(
                partial(
                    extract_document,
                    path,
                    doc.mime_type,
                    settings=settings,
                    language=doc.language,
                    allow_ocr=True,
                    on_ocr_progress=_ocr_progress_callback(loop, doc.id),
                    on_ocr_page=_ocr_page_callback(loop, doc.id, full_text_parts),
                )
            )
        # Pages already persisted via on_ocr_page for paddle path; pillow fallback
        # may not emit pages — ensure rows exist.
        if not full_text_parts and extracted.pages:
            for page_data in extracted.pages:
                session.add(
                    DocumentPage(
                        document_id=doc.id,
                        page_number=page_data.page_number,
                        text=page_data.text,
                    )
                )
                if page_data.text.strip():
                    full_text_parts.append(page_data.text)

    doc.page_count = extracted.page_count or len(extracted.pages)
    doc.extracted_text = "\n\n".join(full_text_parts)
    doc.text_extracted = True
    # Native PDF extract never counts as OCR; images OCR inline during this job.
    if is_pdf:
        doc.ocr_completed = False
    else:
        doc.ocr_completed = extracted.method == "paddleocr" or "ocr" in extracted.method
        if doc.ocr_completed:
            doc.ocr_pages_done = 1
            doc.ocr_pages_total = 1
    doc.language = (
        doc.language or extracted.language or detect_language_hint(doc.extracted_text or "")
    )
    doc.processing_status = ProcessingStatus.PROCESSING
    doc.processing_error = None
    await session.flush()

    page_delta = max(0, (doc.page_count or 0) - prior_page_count)
    counter_deltas: dict[str, int] = {}
    if page_delta:
        counter_deltas["pages_processed"] = page_delta
    if not is_pdf and doc.ocr_completed and page_delta:
        counter_deltas["ocr_pages"] = page_delta
    if counter_deltas:
        await library_stats.bump_counters(session, doc.owner_id, **counter_deltas)

    await refresh_page_search_vectors(session, doc.id)
    await refresh_document_search_vector(session, doc.id)

    # Final indexing is gated behind Inbox "Process documents".
    # Thin/scanned PDFs must finish the dedicated OCR job before AI suggestions.
    if is_pdf and settings.ocr_enabled and pages_need_ocr(extracted.pages):
        await job_service.enqueue_job(
            session,
            job_type=JobType.OCR,
            document_id=doc.id,
            # Ahead of thumbnail so OCR → AI is not stuck behind preview work.
            priority=max((job.priority or 100) - 5, 1),
        )
        logger.info(
            "Enqueued OCR before metadata suggestion for doc=%s (text_len=%s, pages=%s)",
            doc.id,
            len((doc.extracted_text or "").strip()),
            len(extracted.pages),
        )
    else:
        await _enqueue_metadata_suggestion_or_finish(
            session,
            doc,
            priority=job.priority,
            exclude_job_id=job.id,
        )

    return {"page_count": doc.page_count, "method": extracted.method}


async def process_ocr(session: AsyncSession, job: Job) -> dict:
    """Run OCR for scanned PDFs, then enqueue AI filing suggestions."""
    if job.document_id is None:
        raise ValueError("OCR job requires document_id")
    doc = await _get_document(session, job.document_id)
    storage = StorageService()
    path = storage.open_original_path(doc.storage_key)
    settings = get_settings()
    prior_page_count = doc.page_count or 0

    loop = asyncio.get_running_loop()
    try:
        with pymupdf.open(path) as pdf:
            page_total = pdf.page_count
    except Exception:
        page_total = prior_page_count or 0
    if page_total:
        await commit_ocr_progress(doc.id, 0, page_total)

    await clear_document_pages(doc.id)

    full_text_parts: list[str] = []
    # Paddle runs in a short-lived subprocess (default); exclusive gate prevents
    # stacking other jobs on top when JOB_CONCURRENCY > 1.
    async with ocr_exclusive_section():
        extracted = await asyncio.to_thread(
            partial(
                extract_document,
                path,
                doc.mime_type,
                settings=settings,
                language=doc.language,
                force_ocr=True,
                on_ocr_progress=_ocr_progress_callback(loop, doc.id),
                on_ocr_page=_ocr_page_callback(loop, doc.id, full_text_parts),
            )
        )

    if not full_text_parts and extracted.pages:
        for page_data in extracted.pages:
            session.add(
                DocumentPage(
                    document_id=doc.id,
                    page_number=page_data.page_number,
                    text=page_data.text,
                )
            )
            if page_data.text.strip():
                full_text_parts.append(page_data.text)

    doc.extracted_text = "\n\n".join(full_text_parts)
    doc.text_extracted = True
    doc.ocr_completed = True
    if extracted.language and not doc.language:
        doc.language = extracted.language
    elif not doc.language:
        doc.language = detect_language_hint(doc.extracted_text or "")
    ocr_page_count = extracted.page_count or len(extracted.pages)
    doc.page_count = ocr_page_count
    doc.ocr_pages_done = ocr_page_count
    doc.ocr_pages_total = ocr_page_count
    await session.flush()

    counter_deltas: dict[str, int] = {"ocr_pages": ocr_page_count}
    if prior_page_count == 0:
        counter_deltas["pages_processed"] = ocr_page_count
    await library_stats.bump_counters(session, doc.owner_id, **counter_deltas)

    await refresh_page_search_vectors(session, doc.id)
    await refresh_document_search_vector(session, doc.id)

    # OCR replaces page text — drop stale chunks/embeddings/summaries.
    await invalidate_retrieval_artifacts(session, doc)

    logger.info(
        "OCR finished for doc=%s method=%s text_len=%s; enqueueing AI if eligible",
        doc.id,
        extracted.method,
        len((doc.extracted_text or "").strip()),
    )
    await _enqueue_metadata_suggestion_or_finish(
        session,
        doc,
        priority=job.priority,
        exclude_job_id=job.id,
    )

    # Library documents must be re-indexed for RAG after OCR (text changed).
    await _enqueue_library_indexing(
        session,
        doc,
        priority=(job.priority or 100) + 5,
    )

    return {
        "ocr_completed": True,
        "method": extracted.method,
        "text_len": len(doc.extracted_text or ""),
    }


async def process_thumbnail(session: AsyncSession, job: Job) -> dict:
    if job.document_id is None:
        raise ValueError("THUMBNAIL job requires document_id")
    doc = await _get_document(session, job.document_id)
    storage = StorageService()
    path = storage.open_original_path(doc.storage_key)

    try:
        result = await persist_previews(
            storage,
            doc.id,
            path,
            doc.mime_type,
        )
    except Exception as exc:
        logger.warning("Thumbnail skipped for %s: %s", doc.id, exc)
        return {"skipped": True, "reason": str(exc)}

    doc.thumbnail_key = result.thumbnail_key
    doc.preview_key = result.preview_key
    await session.flush()
    return {"thumbnail_key": result.thumbnail_key}


async def process_indexing(session: AsyncSession, job: Job) -> dict:
    if job.document_id is None:
        raise ValueError("INDEXING job requires document_id")
    doc = await _get_document(session, job.document_id)

    pages = (
        (
            await session.execute(
                select(DocumentPage)
                .where(DocumentPage.document_id == doc.id)
                .order_by(DocumentPage.page_number)
            )
        )
        .scalars()
        .all()
    )

    page_inputs = [PageInput(page_number=p.page_number, text=p.text) for p in pages]

    embedding = await resolve_assignment(session, AIWorkloadRole.EMBEDDING)
    caps = resolve_embedding_capabilities(embedding.provider)
    drafts = chunk_pages(page_inputs, limits=caps.chunking_limits())

    await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    # Old embeddings belonged to deleted chunks; clear until EMBEDDING finishes.
    doc.has_embeddings = False
    doc.chunks_embedded = 0
    doc.chunks_failed = 0
    doc.embedding_error = None
    doc.embedding_started_at = None
    doc.embedding_finished_at = None

    for draft in drafts:
        session.add(
            DocumentChunk(
                document_id=doc.id,
                page_number=draft.page_number,
                page_end=draft.page_end,
                section=draft.section,
                chunk_index=draft.chunk_index,
                text=draft.text,
                token_count=draft.token_count,
                content_hash=draft.content_hash,
                chunking_version=draft.chunking_version,
                embedding_status=ChunkEmbeddingStatus.PENDING,
            )
        )

    doc.chunks_total = len(drafts)
    doc.document_indexed = True
    doc.indexed_at = datetime.now(UTC)
    # Keep ready after final indexing (document already left inbox via Process).
    if doc.processing_status != ProcessingStatus.FAILED:
        doc.processing_status = ProcessingStatus.READY
    await session.flush()

    await refresh_document_search_vector(session, doc.id)

    ai_settings = await ensure_ai_settings(session)
    indexing = await resolve_assignment(session, AIWorkloadRole.INDEXING)
    if (
        embedding.provider is not None
        and embedding.model
        and _provider_reachable_for_jobs(embedding.provider)
    ):
        await job_service.enqueue_job(
            session,
            job_type=JobType.EMBEDDING,
            document_id=doc.id,
            priority=job.priority + 10,
        )
    elif embedding.provider is not None and embedding.model:
        logger.info(
            "Skipping EMBEDDING enqueue; provider not healthy (probe=%s) doc=%s",
            embedding.provider.last_probe_status if embedding.provider else None,
            doc.id,
        )

    if (
        ai_settings.auto_enrichment
        and indexing.provider is not None
        and indexing.model
        and _provider_reachable_for_jobs(indexing.provider)
    ):
        await job_service.enqueue_job(
            session,
            job_type=JobType.SUMMARY,
            document_id=doc.id,
            priority=job.priority + 20,
        )
    elif ai_settings.auto_enrichment and indexing.provider is not None and indexing.model:
        logger.info(
            "Skipping SUMMARY enqueue; provider not healthy (probe=%s) doc=%s",
            indexing.provider.last_probe_status if indexing.provider else None,
            doc.id,
        )

    logger.info(
        "Indexed document_id=%s chunks=%s max_tokens=%s",
        doc.id,
        len(drafts),
        caps.chunking_limits().max_tokens,
    )
    return {"chunks": len(drafts)}


async def process_embedding(session: AsyncSession, job: Job) -> dict:
    return await process_document_embeddings(session, job)


async def process_summary(session: AsyncSession, job: Job) -> dict:
    if job.document_id is None:
        raise ValueError("SUMMARY job requires document_id")
    doc = await _get_document(session, job.document_id)
    ai_settings = await ensure_ai_settings(session)
    indexing = await resolve_assignment(session, AIWorkloadRole.INDEXING)
    if not ai_settings.auto_enrichment or indexing.provider is None or not indexing.model:
        return {"skipped": True}

    provider = indexing.provider
    if not provider.enabled:
        return {"skipped": True}
    if not _provider_reachable_for_jobs(provider):
        logger.warning(
            "summary soft-skipped; indexing provider not healthy (probe=%s) doc=%s",
            provider.last_probe_status,
            doc.id,
        )
        return {"skipped": True, "reason": "ai_unavailable"}

    text = (doc.extracted_text or "").strip()
    if len(text) < 50:
        return {"skipped": True, "reason": "insufficient_text"}

    try:
        PrivacyGate(ai_settings, provider).assert_can_qa()
        await assert_ai_quota(session, doc.owner_id)
        adapter = get_adapter(provider)

        prompt = (
            "Summarize the following document in 2-4 concise sentences. "
            "Do not invent facts not present in the text.\n\n"
            f"{text[:12000]}"
        )
        started = time.perf_counter()
        async with provider_chat_guard(provider.id):
            result = await adapter.chat(
                [ChatMessage(role="user", content=prompt)],
                model=indexing.model,
                max_tokens=provider.max_output_tokens or 1024,
                temperature=0.3,
            )
        duration_ms = round((time.perf_counter() - started) * 1000)
        await adapter.aclose()
    except (PrivacyViolationError, ValidationError) as exc:
        logger.warning("summary soft-skipped for doc=%s: %s", doc.id, exc)
        return {"skipped": True, "reason": "ai_unavailable", "detail": str(exc)[:200]}
    except AIProviderError as exc:
        if is_transient_ai_error(exc):
            raise
        logger.warning("summary soft-skipped for doc=%s: %s", doc.id, exc)
        return {"skipped": True, "reason": "ai_unavailable", "detail": str(exc)[:200]}

    doc.ai_summary = result.content.strip()
    doc.ai_summary_meta = {
        "provider": provider.name,
        "model": result.model,
        "generated_at": datetime.now(UTC).isoformat(),
    }
    await session.flush()

    await record_usage(
        session,
        user_id=doc.owner_id,
        provider=provider.name,
        model=result.model,
        operation="summary",
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        reported_cost=result.reported_cost,
        cost_currency=result.cost_currency,
        cost_source="provider" if result.reported_cost is not None else None,
        is_local=provider.is_local,
        document_id=doc.id,
        duration_ms=duration_ms,
    )

    return {"summary_length": len(doc.ai_summary or "")}


_FOLDER_PATH_RE = re.compile(r"^[\w][\w /&'.-]{0,200}$", re.UNICODE)


def _normalize_folder_path(path: str) -> str:
    path = path.strip().strip("/")
    return re.sub(r"\s*/\s*", " / ", path)


def _is_system_folder_path(path: str) -> bool:
    """Inbox / Trash / bare Documents root are not valid filing targets."""
    normalized = path.replace(" / ", "/").strip("/").lower()
    if normalized in {"inbox", "trash", "documents", "documents/inbox", "documents/trash"}:
        return True
    return normalized.endswith("/inbox") or normalized.endswith("/trash")


def _library_relative_folder_path(path: str) -> str:
    """Strip a single leading Documents segment so prompts stay relative to root."""
    normalized = _normalize_folder_path(path)
    parts = [part for part in normalized.split(" / ") if part]
    if parts and parts[0].lower() == "documents":
        parts = parts[1:]
    return " / ".join(parts)


def _parse_suggestion_json(content: str) -> dict:
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            data = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return data if isinstance(data, dict) else {}


def _require_suggestion_json(content: str, *, finish_reason: str | None) -> dict:
    """Parse model output or raise a retryable provider error."""
    data = _parse_suggestion_json(content)
    if data:
        return data
    raise AIProviderError(
        "Metadata suggestion response was truncated or not valid JSON "
        f"(finish_reason={finish_reason or 'unknown'}, content_len={len(content or '')}). "
        "Try again."
    )


# Filing JSON is small; cap output so runaway generations fail fast instead of
# producing ~6k tokens of prose that truncates before valid JSON.
_METADATA_SUGGESTION_MAX_TOKENS = 2048


def _coerce_confidence(value: object) -> float | None:
    """Normalize a model confidence to [0, 1], or None if missing/invalid."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        score = float(value)
    elif isinstance(value, str):
        try:
            score = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    if score != score:  # NaN
        return None
    # Whole-number percents (e.g. 85, "90") → 0–1.
    if score > 1.0 and score <= 100.0 and score == int(score):
        score = score / 100.0
    if score < 0.0 or score > 1.0:
        return None
    return round(score, 4)


def _overall_confidence(data: dict) -> float | None:
    """Average numeric scores from a confidence object or scalar."""
    block = data.get("confidence")
    if isinstance(block, dict):
        values = [_coerce_confidence(v) for v in block.values()]
        nums = [v for v in values if v is not None]
        if nums:
            return round(sum(nums) / len(nums), 4)
        return None
    return _coerce_confidence(block)


def _field_confidence(data: dict, field: str) -> float | None:
    block = data.get("confidence")
    if isinstance(block, dict):
        specific = _coerce_confidence(block.get(field))
        if specific is not None:
            return specific
    if field == "overall":
        return _overall_confidence(data)
    overall = _overall_confidence(data)
    if overall is not None:
        return overall
    return None


def _parse_tag_entries(tags: object) -> list[tuple[str, float | None]]:
    """Parse tags as strings or {name, confidence} objects; dedupe by case."""
    if not isinstance(tags, list):
        return []
    seen: set[str] = set()
    out: list[tuple[str, float | None]] = []
    for entry in tags:
        name: str | None = None
        conf: float | None = None
        if isinstance(entry, str):
            name = entry.strip()
        elif isinstance(entry, dict):
            raw_name = entry.get("name")
            if isinstance(raw_name, str):
                name = raw_name.strip()
            conf = _coerce_confidence(entry.get("confidence"))
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append((name, conf))
        if len(out) >= 12:
            break
    return out


async def process_metadata_suggestion(session: AsyncSession, job: Job) -> dict:
    """Generate filing suggestions for Inbox review (never auto-applied)."""
    if job.document_id is None:
        raise ValueError("METADATA_SUGGESTION job requires document_id")
    doc = await _get_document(session, job.document_id)

    # Hard gate: never file-suggest while OCR is still in flight.
    if await _has_open_ocr_job(session, doc.id, exclude_job_id=job.id):
        logger.info(
            "metadata_suggestion waiting for OCR on doc=%s; skipping this job",
            doc.id,
        )
        return {"skipped": True, "reason": "waiting_for_ocr"}

    settings = get_settings()
    if _pdf_needs_ocr_before_ai(doc, ocr_enabled=settings.ocr_enabled):
        await job_service.enqueue_job(
            session,
            job_type=JobType.OCR,
            document_id=doc.id,
            priority=(job.priority or 50) - 5,
        )
        logger.info(
            "metadata_suggestion enqueued OCR first for doc=%s; skipping this job",
            doc.id,
        )
        return {"skipped": True, "reason": "enqueued_ocr_first"}

    ai_settings = await ensure_ai_settings(session)
    indexing = await resolve_assignment(session, AIWorkloadRole.INDEXING)
    manual = bool((job.payload or {}).get("manual"))
    if indexing.provider is None or not indexing.model:
        if manual:
            raise ValueError("No indexing model assigned for suggestions")
        await mark_preflight_ready(session, doc.id, exclude_job_id=job.id)
        return {"skipped": True, "reason": "auto_tagging_disabled"}
    if not manual and not ai_settings.auto_tagging:
        await mark_preflight_ready(session, doc.id, exclude_job_id=job.id)
        return {"skipped": True, "reason": "auto_tagging_disabled"}

    provider = indexing.provider
    if not provider.enabled:
        if manual:
            raise ValueError("Indexing provider is disabled")
        await mark_preflight_ready(session, doc.id, exclude_job_id=job.id)
        return {"skipped": True, "reason": "provider_unavailable"}

    text = (doc.extracted_text or "").strip()
    if len(text) < _MIN_TEXT_FOR_AI:
        if manual:
            raise ValueError("Not enough extracted text for suggestions")
        doc.needs_review = True
        await mark_preflight_ready(session, doc.id, exclude_job_id=job.id)
        return {"skipped": True, "reason": "insufficient_text"}

    folders = (
        (
            await session.execute(
                select(Folder).where(
                    Folder.owner_id == doc.owner_id,
                    Folder.is_trashed.is_(False),
                    Folder.kind == FolderKind.NORMAL,
                )
            )
        )
        .scalars()
        .all()
    )
    folder_id_by_path: dict[str, uuid.UUID] = {}
    all_folder_paths: list[str] = []
    for folder in folders:
        if not folder.path_cache or _is_system_folder_path(folder.path_cache):
            continue
        rel = _library_relative_folder_path(folder.path_cache)
        if not rel or _is_system_folder_path(rel):
            continue
        if rel not in folder_id_by_path:
            folder_id_by_path[rel] = folder.id
            all_folder_paths.append(rel)

    types = (
        (await session.execute(select(DocumentType).where(DocumentType.owner_id == doc.owner_id)))
        .scalars()
        .all()
    )
    correspondents = (
        (await session.execute(select(Correspondent).where(Correspondent.owner_id == doc.owner_id)))
        .scalars()
        .all()
    )
    tags = (await session.execute(select(Tag).where(Tag.owner_id == doc.owner_id))).scalars().all()

    type_names = [t.name for t in types]
    correspondent_names = [c.name for c in correspondents]

    page_rows = (
        (
            await session.execute(
                select(DocumentPage)
                .where(DocumentPage.document_id == doc.id)
                .order_by(DocumentPage.page_number)
            )
        )
        .scalars()
        .all()
    )
    try:
        filing_sample = build_filing_sample(
            filename=doc.original_filename or "",
            pages=[PageText(page_number=p.page_number, text=p.text or "") for p in page_rows],
            extracted_text=text,
            page_count=doc.page_count,
        )
        document_block = format_filing_document_block(filing_sample)
        sample_text = filing_sample.document_text
    except Exception:
        logger.exception(
            "filing sample failed for doc=%s; falling back to prefix truncation",
            doc.id,
        )
        document_block = (
            f"Filename: {doc.original_filename}\n"
            f"Document text:\n{legacy_prefix_fallback(text)}"
        )
        sample_text = legacy_prefix_fallback(text)
    else:
        # Filename is already present in signals; keep an explicit line for models.
        document_block = f"Filename: {doc.original_filename}\n\n{document_block}"

    query_tokens = tokenize_for_candidates(doc.original_filename or "", sample_text)

    folder_counts: dict[str, int] = {}
    if folder_id_by_path:
        count_rows = (
            await session.execute(
                select(Document.folder_id, func.count())
                .where(
                    Document.owner_id == doc.owner_id,
                    Document.is_trashed.is_(False),
                    Document.folder_id.in_(list(folder_id_by_path.values())),
                )
                .group_by(Document.folder_id)
            )
        ).all()
        id_to_path = {folder_id: path for path, folder_id in folder_id_by_path.items()}
        for folder_id, count in count_rows:
            path = id_to_path.get(folder_id)
            if path is not None:
                folder_counts[path] = int(count)

    folder_paths = rank_folder_candidates(
        all_folder_paths,
        query_tokens=query_tokens,
        document_counts=folder_counts,
        filename=doc.original_filename,
    )

    tag_usage_rows = (
        await session.execute(
            select(Tag.id, func.count(DocumentTag.document_id))
            .outerjoin(DocumentTag, DocumentTag.tag_id == Tag.id)
            .where(Tag.owner_id == doc.owner_id)
            .group_by(Tag.id)
        )
    ).all()
    usage_by_id = {tag_id: int(count) for tag_id, count in tag_usage_rows}
    tag_names = rank_tag_candidates(
        [(t.name, usage_by_id.get(t.id, 0)) for t in tags],
        query_tokens=query_tokens,
    )

    prompt = (
        "You help file documents into a personal archive. "
        "Return ONLY valid JSON with keys: "
        "folder_path (string using ' / ' separators, or null), "
        "create_folder (boolean — true if folder_path is not in Existing folder candidates), "
        "title (string or null), "
        "document_type (string name or null), "
        "correspondent (string name or null), "
        "tags (array of objects {name: string, confidence: number 0-1}; "
        "legacy string tags are also accepted), "
        "confidence (object with optional folder, title, document_type, "
        "correspondent scores as numbers 0-1), "
        "needs_review (boolean — true if unsure).\n\n"
        "Confidence rules:\n"
        "- Scores must be between 0 and 1 (higher = more sure).\n"
        "- Put per-tag confidence on each tags entry.\n"
        "- Put other field scores under confidence.\n\n"
        "Folder rules:\n"
        "- Prefer a specific filing destination from the document subject "
        "(person, org, topic, year), e.g. 'Topic / PersonOrOrg' "
        "for an identity document or 'Category / Year' for a dated record.\n"
        "- Prefer an Existing folder candidate when it clearly fits; otherwise invent a "
        "new path and set create_folder true.\n"
        "- Do not copy example paths literally; choose from candidates or invent "
        "from the document.\n"
        "- Resumes and CVs: prefer Job Hunt / career paths (or invent 'Job Hunt'); "
        "never file them under Finance, Salary, payroll, or payslip folders.\n"
        "- Never suggest Inbox, Trash, or Documents (alone or as Documents / Inbox).\n"
        "- Do not prefix paths with Documents; Existing folders are relative to the library root.\n"
        "- Paths must use ' / ' between segments (not underscores).\n\n"
        "Tag rules:\n"
        "- Prefer Existing tag candidates only when they clearly fit this document.\n"
        "- If the candidate list is empty or weak, invent new topical tags from the document.\n"
        "- Never reuse unrelated catalogue tags (skills, schools, ID types) just because "
        "they appear in candidates.\n"
        "- Suggest at most 5 high-confidence tags.\n\n"
        f"Existing folder candidates:\n{json.dumps(folder_paths)}\n"
        f"Existing document types:\n{json.dumps(type_names)}\n"
        f"Existing correspondents:\n{json.dumps(correspondent_names)}\n"
        f"Existing tag candidates:\n{json.dumps(tag_names)}\n\n"
        f"{document_block}"
    )

    try:
        PrivacyGate(ai_settings, provider).assert_can_qa()
        await assert_ai_quota(session, doc.owner_id)

        adapter = get_adapter(provider)
        # Thinking models (e.g. Qwen3) spend large budgets on reasoning_content
        # before emitting the final JSON in content. Cap output so truncation
        # fails fast and retries instead of silently producing zero suggestions.
        max_tokens = _METADATA_SUGGESTION_MAX_TOKENS
        if provider.max_output_tokens is not None:
            max_tokens = min(max_tokens, provider.max_output_tokens)
        started = time.perf_counter()
        async with provider_chat_guard(provider.id):
            result = await adapter.chat(
                [ChatMessage(role="user", content=prompt)],
                model=indexing.model,
                max_tokens=max_tokens,
                temperature=0.2,
            )
        duration_ms = round((time.perf_counter() - started) * 1000)
        await adapter.aclose()
    except (PrivacyViolationError, ValidationError) as exc:
        if manual:
            raise
        logger.warning(
            "metadata_suggestion soft-skipped for doc=%s: %s",
            doc.id,
            exc,
        )
        doc.needs_review = True
        await mark_preflight_ready(session, doc.id, exclude_job_id=job.id)
        return {"skipped": True, "reason": "ai_unavailable", "detail": str(exc)[:200]}
    except AIProviderError as exc:
        if manual or is_transient_ai_error(exc):
            raise
        logger.warning(
            "metadata_suggestion soft-skipped for doc=%s: %s",
            doc.id,
            exc,
        )
        doc.needs_review = True
        await mark_preflight_ready(session, doc.id, exclude_job_id=job.id)
        return {"skipped": True, "reason": "ai_unavailable", "detail": str(exc)[:200]}

    data = _require_suggestion_json(result.content, finish_reason=result.finish_reason)
    created = 0

    # Replace prior pending suggestions only after we have valid JSON to apply.
    await session.execute(
        delete(AISuggestion).where(
            AISuggestion.document_id == doc.id,
            AISuggestion.status == SuggestionStatus.PENDING,
        )
    )

    field_scores = {
        "folder": _field_confidence(data, "folder"),
        "title": _field_confidence(data, "title"),
        "document_type": _field_confidence(data, "document_type"),
        "correspondent": _field_confidence(data, "correspondent"),
    }
    overall_confidence = _overall_confidence(data)

    folder_path = data.get("folder_path")
    if isinstance(folder_path, str):
        folder_path = _library_relative_folder_path(folder_path)
        if (
            folder_path
            and not _is_system_folder_path(folder_path)
            and _FOLDER_PATH_RE.match(folder_path.replace(" / ", "/"))
        ):
            relative = folder_path
            relative_slash = relative.replace(" / ", "/")
            existing = next(
                (
                    f
                    for f in folders
                    if _library_relative_folder_path(f.path_cache or "") == relative
                    or (f.path_cache or "").replace(" / ", "/") == relative_slash
                    or (f.path_cache or "") == relative
                ),
                None,
            )
            create_folder = existing is None
            if existing is None and "/" not in relative_slash:
                leaf = relative.lower()
                for f in folders:
                    cache_rel = _library_relative_folder_path(f.path_cache or "")
                    if cache_rel.lower() == leaf or cache_rel.lower().endswith(" / " + leaf):
                        existing = f
                        create_folder = False
                        break
            value: dict = {
                "path": (
                    _library_relative_folder_path(existing.path_cache)
                    if existing and existing.path_cache
                    else relative
                ),
                "exists": existing is not None,
                "create": create_folder,
            }
            if existing is not None:
                value["folder_id"] = str(existing.id)
            session.add(
                AISuggestion(
                    document_id=doc.id,
                    field="folder",
                    value=value,
                    status=SuggestionStatus.PENDING,
                    provider=provider.name,
                    model=result.model,
                    confidence=field_scores["folder"],
                )
            )
            created += 1
        elif folder_path and _is_system_folder_path(folder_path):
            logger.info(
                "metadata_suggestion ignored a system folder for doc=%s",
                doc.id,
            )

    title = data.get("title")
    if isinstance(title, str) and title.strip():
        session.add(
            AISuggestion(
                document_id=doc.id,
                field="title",
                value={"title": title.strip()[:512]},
                status=SuggestionStatus.PENDING,
                provider=provider.name,
                model=result.model,
                confidence=field_scores["title"],
            )
        )
        created += 1

    doc_type_name = data.get("document_type")
    if isinstance(doc_type_name, str) and doc_type_name.strip():
        match = next(
            (t for t in types if t.name.lower() == doc_type_name.strip().lower()),
            None,
        )
        if match is not None:
            session.add(
                AISuggestion(
                    document_id=doc.id,
                    field="document_type",
                    value={
                        "document_type_id": str(match.id),
                        "name": match.name,
                    },
                    status=SuggestionStatus.PENDING,
                    provider=provider.name,
                    model=result.model,
                    confidence=field_scores["document_type"],
                )
            )
            created += 1

    corr_name = data.get("correspondent")
    if isinstance(corr_name, str) and corr_name.strip():
        match = next(
            (c for c in correspondents if c.name.lower() == corr_name.strip().lower()),
            None,
        )
        if match is not None:
            session.add(
                AISuggestion(
                    document_id=doc.id,
                    field="correspondent",
                    value={
                        "correspondent_id": str(match.id),
                        "name": match.name,
                    },
                    status=SuggestionStatus.PENDING,
                    provider=provider.name,
                    model=result.model,
                    confidence=field_scores["correspondent"],
                )
            )
            created += 1

    for tag_name, tag_conf in _parse_tag_entries(data.get("tags")):
        session.add(
            AISuggestion(
                document_id=doc.id,
                field="tags",
                value={"tag_names": [tag_name]},
                status=SuggestionStatus.PENDING,
                provider=provider.name,
                model=result.model,
                confidence=tag_conf if tag_conf is not None else overall_confidence,
            )
        )
        created += 1

    needs_review = bool(data.get("needs_review"))
    if not folder_path:
        needs_review = True
    doc.needs_review = needs_review

    await session.flush()
    await record_usage(
        session,
        user_id=doc.owner_id,
        provider=provider.name,
        model=result.model,
        operation="metadata_suggestion",
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        reported_cost=result.reported_cost,
        cost_currency=result.cost_currency,
        cost_source="provider" if result.reported_cost is not None else None,
        is_local=provider.is_local,
        document_id=doc.id,
        duration_ms=duration_ms,
    )
    await mark_preflight_ready(session, doc.id, exclude_job_id=job.id)
    return {"suggestions": created, "needs_review": needs_review}


async def process_backup(session: AsyncSession, job: Job) -> dict:
    from lesspaper_ngl.services import backup as backup_service

    return await backup_service.run_backup_job(session, job)


async def process_backup_verify(session: AsyncSession, job: Job) -> dict:
    from lesspaper_ngl.services import backup as backup_service

    return await backup_service.run_verify_job(session, job)


async def process_job(session: AsyncSession, job: Job) -> dict:
    """Dispatch a job to the appropriate handler."""
    handlers = {
        JobType.TEXT_EXTRACTION: process_text_extraction,
        JobType.OCR: process_ocr,
        JobType.THUMBNAIL: process_thumbnail,
        JobType.INDEXING: process_indexing,
        JobType.EMBEDDING: process_embedding,
        JobType.SUMMARY: process_summary,
        JobType.METADATA_SUGGESTION: process_metadata_suggestion,
        JobType.BACKUP: process_backup,
        JobType.BACKUP_VERIFY: process_backup_verify,
    }
    handler = handlers.get(job.job_type)
    if handler is None:
        return {"skipped": True, "reason": f"unsupported job type: {job.job_type.value}"}
    return await handler(session, job)


async def process_consume_file(
    session: AsyncSession, path, storage: StorageService | None = None
) -> uuid.UUID | None:
    """Ingest a consume-folder file after stability and checksum verification.

    Files at the consume root go to Inbox. Nested paths recreate lesspaper-ngl folders
    under Documents root (e.g. ``consume/Finance/a.pdf`` → ``Documents / Finance``).

    Content duplicates (same SHA-256) are skipped and the source file is removed.
    """
    from pathlib import Path

    from lesspaper_ngl.services.documents import ingest_path

    storage = storage or StorageService()
    source = Path(path)
    if not source.is_file():
        return None

    consume_root = storage.settings.consume_path.resolve()
    try:
        rel = source.resolve().relative_to(consume_root)
    except ValueError:
        rel = Path(source.name)

    relative_path = None if len(rel.parts) <= 1 else str(rel.as_posix())
    from lesspaper_ngl.services import users as user_service

    owner = await user_service.resolve_consume_owner(session)

    result = await ingest_path(
        session,
        source,
        owner_id=owner.id,
        storage=storage,
        relative_path=relative_path,
        on_duplicate="skip",
        # Nested consume paths nest under Documents root; flat files use Inbox
        # via ingest_bytes default when relative_path is None.
        folder_id=None,
    )

    if result.status == "duplicate":
        source.unlink(missing_ok=True)
        return uuid.UUID(result.existing_document_id) if result.existing_document_id else None

    assert result.document is not None
    if storage.sha256_file(source) != result.document.checksum:
        raise ValueError("Checksum mismatch after ingest — source file retained")

    source.unlink(missing_ok=True)
    return result.document.id
