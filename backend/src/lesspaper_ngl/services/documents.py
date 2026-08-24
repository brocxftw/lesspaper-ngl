"""Document ingestion and metadata services."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from lesspaper_ngl.core.exceptions import DuplicateDocumentError, NotFoundError, ValidationError
from lesspaper_ngl.core.files import (
    assert_allowed_mime,
    detect_mime,
    extension_for_mime,
    normalize_filename,
    split_relative_path,
)
from lesspaper_ngl.models import (
    Correspondent,
    Document,
    DocumentChunk,
    DocumentType,
    Folder,
    FolderKind,
    Job,
    JobStatus,
    JobType,
    ProcessingStatus,
    Tag,
)
from lesspaper_ngl.services import folders as folder_service
from lesspaper_ngl.services import library_stats
from lesspaper_ngl.services.jobs import enqueue_job
from lesspaper_ngl.services.quotas import assert_storage_quota
from lesspaper_ngl.storage.service import StorageService

INBOX_FOLDER_PATH_KEY = "inbox_folder_path"
_MIN_TEXT_FOR_SUGGESTIONS = 20

InboxStatus = Literal["preparing", "ready", "needs_review", "failed"]


async def _cancel_open_jobs(
    session: AsyncSession,
    document_id: uuid.UUID,
    job_types: list[JobType],
) -> None:
    open_jobs = (
        await session.execute(
            select(Job).where(
                Job.document_id == document_id,
                Job.job_type.in_(job_types),
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
    ).scalars().all()
    for job in open_jobs:
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(UTC)
        job.locked_by = None
        job.available_at = None


async def invalidate_retrieval_artifacts(
    session: AsyncSession,
    doc: Document,
) -> None:
    """Clear chunk/embedding/summary state after OCR or text changes.

    Callers must refresh page/document FTS separately after page text updates,
    then re-enqueue INDEXING when the document belongs in the library.
    """
    await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == doc.id))
    doc.document_indexed = False
    doc.indexed_at = None
    doc.has_embeddings = False
    doc.chunks_total = None
    doc.chunks_embedded = None
    doc.chunks_failed = None
    doc.embedding_error = None
    doc.embedding_started_at = None
    doc.embedding_finished_at = None
    doc.ai_summary = None
    doc.ai_summary_meta = None
    doc.modified_date = datetime.now(UTC)
    await session.flush()


@dataclass(slots=True)
class IngestResult:
    status: Literal["created", "duplicate"]
    document: Document | None = None
    existing_document_id: str | None = None
    relative_path: str | None = None


def get_pending_folder_path(doc: Document) -> str | None:
    fields = doc.custom_fields or {}
    raw = fields.get(INBOX_FOLDER_PATH_KEY)
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def set_pending_folder_path(doc: Document, path: str | None) -> None:
    fields = dict(doc.custom_fields or {})
    if path and path.strip():
        fields[INBOX_FOLDER_PATH_KEY] = path.strip()
    else:
        fields.pop(INBOX_FOLDER_PATH_KEY, None)
    doc.custom_fields = fields


def _folder_segments(path: str) -> list[str]:
    normalized = path.replace("\\", "/").strip().strip("/")
    parts = [p.strip() for p in re.split(r"[/]+", normalized.replace(" / ", "/"))]
    return [p for p in parts if p]


def compute_inbox_status(doc: Document) -> InboxStatus | None:
    """Derive user-facing Inbox queue status (None when not in inbox)."""
    if not doc.inbox:
        return None
    if doc.processing_status == ProcessingStatus.FAILED:
        return "failed"
    if doc.processing_status in {ProcessingStatus.PENDING, ProcessingStatus.PROCESSING}:
        return "preparing"
    pending = get_pending_folder_path(doc)
    in_system_inbox = doc.folder is not None and doc.folder.kind == FolderKind.INBOX
    has_target = bool(pending) or (doc.folder is not None and not in_system_inbox)
    if not has_target or doc.needs_review:
        return "needs_review"
    return "ready"


async def find_by_checksum(
    session: AsyncSession, checksum: str, owner_id: uuid.UUID
) -> Document | None:
    return (
        await session.execute(
            select(Document)
            .where(
                Document.owner_id == owner_id,
                Document.checksum == checksum,
                Document.is_trashed.is_(False),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


async def find_trashed_by_checksum(
    session: AsyncSession, checksum: str, owner_id: uuid.UUID
) -> Document | None:
    return (
        await session.execute(
            select(Document)
            .where(
                Document.owner_id == owner_id,
                Document.checksum == checksum,
                Document.is_trashed.is_(True),
            )
            .limit(1)
        )
    ).scalar_one_or_none()


def _document_options() -> tuple:
    return (
        selectinload(Document.tags),
        selectinload(Document.document_type),
        selectinload(Document.correspondent),
        selectinload(Document.folder),
    )


async def get_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    owner_id: uuid.UUID | None = None,
) -> Document:
    result = await session.execute(
        select(Document).options(*_document_options()).where(Document.id == document_id)
    )
    doc = result.scalar_one_or_none()
    if doc is None or (owner_id is not None and doc.owner_id != owner_id):
        raise NotFoundError("Document not found")
    return doc


async def ingest_bytes(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    data: bytes,
    filename: str,
    folder_id: uuid.UUID | None = None,
    relative_path: str | None = None,
    on_duplicate: Literal["error", "skip"] = "error",
    storage: StorageService | None = None,
    priority: int = 50,
) -> IngestResult:
    """Ingest file bytes into content-addressed storage.

    Duplicate policy (SHA-256 of file contents):
    - ``error`` (default): raise ``DuplicateDocumentError`` (HTTP 409)
      when an active document already has this checksum
    - ``skip``: return ``status=duplicate`` without creating a second document
      when an active document already has this checksum
    - If the only match is trashed: permanently delete it and re-ingest
      (fresh document id and processing jobs)

    Physical storage remains content-addressed — one blob per checksum.
    Logical lesspaper-ngl folders are metadata only. A ``relative_path`` with folder
    segments and no ``folder_id`` enters Inbox with a pending folder path
    (materialized on Process). With an explicit ``folder_id``, the tree is
    created under that parent immediately (library import).
    """
    storage = storage or StorageService()
    rel = relative_path.strip() if relative_path else None
    if rel:
        segments, filename = split_relative_path(rel)
    else:
        segments = []
        filename = normalize_filename(filename)

    if not data:
        raise ValidationError("Empty file")
    from lesspaper_ngl.core.config import get_settings

    if len(data) > get_settings().max_upload_bytes:
        raise ValidationError("File exceeds upload size limit")

    mime = detect_mime(data, filename)
    assert_allowed_mime(mime)
    checksum = storage.sha256_bytes(data)

    existing = await find_by_checksum(session, checksum, owner_id)
    if existing is not None:
        if on_duplicate == "skip":
            await library_stats.bump_counters(
                session,
                owner_id,
                duplicates_rejected=1,
            )
            return IngestResult(
                status="duplicate",
                existing_document_id=str(existing.id),
                relative_path=rel,
            )
        raise DuplicateDocumentError(
            "Document already exists",
            existing_document_id=str(existing.id),
        )

    trashed = await find_trashed_by_checksum(session, checksum, owner_id)
    if trashed is not None:
        await permanently_delete(
            session,
            trashed.id,
            owner_id=owner_id,
            storage=storage,
        )

    await assert_storage_quota(session, owner_id, len(data))

    pending_folder_path: str | None = None
    if segments and folder_id is None:
        # Folder/tree upload with no library parent → Inbox + pending path.
        inbox = await folder_service.get_inbox(session, owner_id)
        folder_id = inbox.id
        inbox_flag = True
        pending_folder_path = "/".join(segments)
    elif segments:
        # Explicit library parent: materialize the tree under that folder now.
        await folder_service.get_folder(session, folder_id, owner_id=owner_id)
        leaf = await folder_service.ensure_folder_path(
            session, parent_id=folder_id, segments=segments
        )
        folder_id = leaf.id
        inbox_flag = leaf.kind == FolderKind.INBOX
    elif folder_id is None:
        inbox = await folder_service.get_inbox(session, owner_id)
        folder_id = inbox.id
        inbox_flag = True
    else:
        folder = await folder_service.get_folder(session, folder_id, owner_id=owner_id)
        inbox_flag = folder.kind == FolderKind.INBOX

    ext = extension_for_mime(mime, filename)
    storage_key = await storage.persist_original(data, checksum=checksum, extension=ext)
    title = Path(filename).stem or filename

    doc = Document(
        owner_id=owner_id,
        title=title,
        original_filename=filename,
        storage_key=storage_key,
        checksum=checksum,
        mime_type=mime,
        file_size=len(data),
        folder_id=folder_id,
        processing_status=ProcessingStatus.PENDING,
        inbox=inbox_flag,
        custom_fields={},
    )
    session.add(doc)
    await session.flush()
    if pending_folder_path:
        set_pending_folder_path(doc, pending_folder_path)
        await session.flush()

    await enqueue_job(
        session,
        job_type=JobType.TEXT_EXTRACTION,
        document_id=doc.id,
        priority=priority,
    )
    await enqueue_job(
        session,
        job_type=JobType.THUMBNAIL,
        document_id=doc.id,
        priority=priority + 10,
    )
    created = await get_document(session, doc.id, owner_id=owner_id)
    await library_stats.bump_counters(
        session,
        owner_id,
        documents_ingested=1,
        bytes_ingested=len(data),
    )
    return IngestResult(status="created", document=created, relative_path=rel)


async def ingest_path(
    session: AsyncSession,
    path: Path,
    *,
    owner_id: uuid.UUID,
    storage: StorageService | None = None,
    priority: int = 80,
    folder_id: uuid.UUID | None = None,
    relative_path: str | None = None,
    on_duplicate: Literal["error", "skip"] = "error",
) -> IngestResult:
    storage = storage or StorageService()
    data = path.read_bytes()
    return await ingest_bytes(
        session,
        owner_id=owner_id,
        data=data,
        filename=path.name,
        folder_id=folder_id,
        relative_path=relative_path,
        on_duplicate=on_duplicate,
        storage=storage,
        priority=priority,
    )


async def move_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    folder_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    preserve_inbox: bool | None = None,
) -> Document:
    doc = await get_document(session, document_id, owner_id=owner_id)
    folder = await folder_service.get_folder(session, folder_id, owner_id=owner_id)
    if folder.kind.value == "trash":
        raise ValidationError("Use trash endpoint to move documents to Trash")
    keep_inbox = doc.inbox if preserve_inbox is None else preserve_inbox
    # While reviewing in Inbox, folder assignment must not eject from the queue.
    if preserve_inbox is None and doc.inbox:
        keep_inbox = True
    doc.folder_id = folder_id
    doc.inbox = keep_inbox if keep_inbox else folder.kind.value == "inbox"
    if doc.inbox:
        set_pending_folder_path(doc, None)
        if folder.kind != FolderKind.INBOX:
            doc.needs_review = False
    else:
        set_pending_folder_path(doc, None)
    doc.is_trashed = False
    doc.trashed_at = None
    doc.modified_date = datetime.now(UTC)
    await session.flush()
    session.expire(doc, ["folder"])
    return await get_document(session, doc.id, owner_id=owner_id)


async def trash_document(
    session: AsyncSession, document_id: uuid.UUID, *, owner_id: uuid.UUID
) -> Document:
    doc = await get_document(session, document_id, owner_id=owner_id)
    if doc.is_trashed:
        return doc
    trash = await folder_service.get_trash(session, owner_id)
    doc.trashed_from_folder_id = doc.folder_id
    doc.folder_id = trash.id
    doc.is_trashed = True
    doc.trashed_at = datetime.now(UTC)
    doc.inbox = False
    doc.modified_date = datetime.now(UTC)
    await session.flush()
    return await get_document(session, doc.id, owner_id=owner_id)


async def restore_document(
    session: AsyncSession,
    document_id: uuid.UUID,
    folder_id: uuid.UUID | None = None,
    *,
    owner_id: uuid.UUID,
) -> Document:
    doc = await get_document(session, document_id, owner_id=owner_id)
    if not doc.is_trashed:
        return doc

    target_id = folder_id
    if target_id is None and doc.trashed_from_folder_id is not None:
        origin = await session.get(Folder, doc.trashed_from_folder_id)
        if (
            origin is not None
            and origin.owner_id == owner_id
            and not origin.is_trashed
            and origin.kind != FolderKind.TRASH
        ):
            target_id = origin.id

    if target_id is None:
        inbox = await folder_service.get_inbox(session, owner_id)
        target_id = inbox.id
    else:
        target = await folder_service.get_folder(session, target_id, owner_id=owner_id)
        if target.is_trashed or target.kind == FolderKind.TRASH:
            inbox = await folder_service.get_inbox(session, owner_id)
            target_id = inbox.id

    doc.folder_id = target_id
    doc.is_trashed = False
    doc.trashed_at = None
    doc.trashed_from_folder_id = None
    doc.inbox = target_id == (await folder_service.get_inbox(session, owner_id)).id
    doc.modified_date = datetime.now(UTC)
    await session.flush()
    return await get_document(session, doc.id, owner_id=owner_id)


async def permanently_delete(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    owner_id: uuid.UUID | None = None,
    storage: StorageService | None = None,
    allow_inbox: bool = False,
) -> None:
    storage = storage or StorageService()
    doc = await get_document(session, document_id, owner_id=owner_id)
    if not doc.is_trashed and not (allow_inbox and doc.inbox):
        raise ValidationError("Document must be in Trash before permanent deletion")
    await library_stats.bump_counters(
        session,
        doc.owner_id,
        purged_documents=1,
    )
    storage_key = doc.storage_key
    thumb = doc.thumbnail_key
    preview = doc.preview_key
    shared_storage = (
        await session.execute(
            select(func.count())
            .select_from(Document)
            .where(
                Document.storage_key == storage_key,
                Document.id != doc.id,
            )
        )
    ).scalar_one()
    await session.delete(doc)
    await session.flush()
    if not shared_storage:
        await storage.delete_original(storage_key)
    await storage.delete_derived("thumbnail", thumb)
    await storage.delete_derived("preview", preview)


async def remove_from_queue(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    storage: StorageService | None = None,
) -> None:
    """Permanently remove an Inbox document without library Trash."""
    doc = await get_document(session, document_id, owner_id=owner_id)
    if not doc.inbox:
        raise ValidationError("Only Inbox documents can be removed from the queue")
    if doc.is_trashed:
        raise ValidationError("Document is already in Trash")
    await permanently_delete(
        session,
        document_id,
        owner_id=owner_id,
        storage=storage,
        allow_inbox=True,
    )


async def retry_preflight(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    priority: int = 50,
) -> Document:
    doc = await get_document(session, document_id, owner_id=owner_id)
    if not doc.inbox:
        raise ValidationError("Only Inbox documents can retry pre-flight")
    # Cancel open preflight jobs
    open_jobs = (
        await session.execute(
            select(Job).where(
                Job.document_id == doc.id,
                Job.job_type.in_(
                    [
                        JobType.TEXT_EXTRACTION,
                        JobType.OCR,
                        JobType.METADATA_SUGGESTION,
                    ]
                ),
                Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            )
        )
    ).scalars().all()
    for job in open_jobs:
        job.status = JobStatus.CANCELLED
        job.completed_at = datetime.now(UTC)
        job.locked_by = None

    doc.processing_status = ProcessingStatus.PENDING
    doc.processing_error = None
    doc.text_extracted = False
    doc.ocr_completed = False
    doc.ocr_pages_done = None
    doc.ocr_pages_total = None
    doc.modified_date = datetime.now(UTC)
    await session.flush()

    await enqueue_job(
        session,
        job_type=JobType.TEXT_EXTRACTION,
        document_id=doc.id,
        priority=priority,
    )
    await enqueue_job(
        session,
        job_type=JobType.THUMBNAIL,
        document_id=doc.id,
        priority=priority + 10,
    )
    return await get_document(session, doc.id, owner_id=owner_id)


async def retry_ocr(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    priority: int = 45,
) -> Document:
    """Re-run OCR after invalidating retrieval artifacts.

    Safe for library documents: chunks, embeddings, and summaries are cleared
    first; INDEXING is enqueued after OCR completes (non-inbox path).
    """
    doc = await get_document(session, document_id, owner_id=owner_id)

    await _cancel_open_jobs(
        session,
        doc.id,
        [JobType.OCR, JobType.INDEXING, JobType.EMBEDDING, JobType.SUMMARY],
    )

    await invalidate_retrieval_artifacts(session, doc)
    doc.ocr_completed = False
    doc.ocr_pages_done = None
    doc.ocr_pages_total = None
    doc.processing_status = ProcessingStatus.PROCESSING
    doc.processing_error = None
    await session.flush()

    await enqueue_job(
        session,
        job_type=JobType.OCR,
        document_id=doc.id,
        priority=priority,
    )
    return await get_document(session, doc.id, owner_id=owner_id)


async def reprocess_embeddings(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    priority: int = 50,
) -> Document:
    """Clear existing vectors and enqueue a fresh EMBEDDING job."""
    from lesspaper_ngl.ai.assignments import resolve_assignment
    from lesspaper_ngl.models import AIWorkloadRole

    doc = await get_document(session, document_id, owner_id=owner_id)
    if not doc.document_indexed:
        raise ValidationError("Document must be indexed before re-embedding")

    chunks = (
        (
            await session.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
            )
        )
        .scalars()
        .all()
    )
    if not chunks:
        raise ValidationError("No indexed chunks available to embed")

    embedding = await resolve_assignment(session, AIWorkloadRole.EMBEDDING)
    if embedding.provider is None or not embedding.model:
        raise ValidationError("No embedding model is assigned")
    if not embedding.provider.enabled:
        raise ValidationError("Assigned embedding provider is disabled")

    await _cancel_open_jobs(session, doc.id, [JobType.EMBEDDING])

    from lesspaper_ngl.services.embedding_pipeline import reset_chunk_embeddings

    await reset_chunk_embeddings(session, doc.id)
    doc.has_embeddings = False
    doc.chunks_embedded = 0
    doc.chunks_failed = 0
    doc.embedding_error = None
    doc.embedding_started_at = None
    doc.embedding_finished_at = None
    doc.modified_date = datetime.now(UTC)
    if doc.processing_status == ProcessingStatus.PARTIAL:
        doc.processing_status = ProcessingStatus.READY
    await session.flush()

    await enqueue_job(
        session,
        job_type=JobType.EMBEDDING,
        document_id=doc.id,
        priority=priority,
    )
    return await get_document(session, doc.id, owner_id=owner_id)


async def reprocess_suggestions(
    session: AsyncSession,
    document_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    priority: int = 70,
) -> Document:
    """Enqueue a manual metadata suggestion pass (tags, folder, title, etc.)."""
    from lesspaper_ngl.ai.assignments import resolve_assignment
    from lesspaper_ngl.models import AIWorkloadRole

    doc = await get_document(session, document_id, owner_id=owner_id)
    text = (doc.extracted_text or "").strip()
    if len(text) < _MIN_TEXT_FOR_SUGGESTIONS:
        raise ValidationError("Not enough extracted text for suggestions")

    indexing = await resolve_assignment(session, AIWorkloadRole.INDEXING)
    if indexing.provider is None or not indexing.model:
        raise ValidationError("No indexing model is assigned")
    if not indexing.provider.enabled:
        raise ValidationError("Assigned indexing provider is disabled")

    await _cancel_open_jobs(session, doc.id, [JobType.METADATA_SUGGESTION])

    await enqueue_job(
        session,
        job_type=JobType.METADATA_SUGGESTION,
        document_id=doc.id,
        priority=priority,
        payload={"manual": True},
    )
    return await get_document(session, doc.id, owner_id=owner_id)


async def process_inbox_documents(
    session: AsyncSession,
    document_ids: list[uuid.UUID],
    *,
    owner_id: uuid.UUID,
    priority: int = 40,
) -> dict[str, list[dict]]:
    """Commit reviewed Inbox documents into the library and enqueue final indexing."""
    processed: list[dict] = []
    skipped: list[dict] = []
    failed: list[dict] = []

    for doc_id in document_ids:
        try:
            doc = await get_document(session, doc_id, owner_id=owner_id)
        except NotFoundError:
            skipped.append({"id": str(doc_id), "reason": "not_found"})
            continue

        if not doc.inbox:
            skipped.append({"id": str(doc.id), "reason": "not_in_inbox"})
            continue
        if doc.processing_status == ProcessingStatus.FAILED:
            skipped.append({"id": str(doc.id), "reason": "failed_preflight"})
            continue
        if doc.processing_status in {
            ProcessingStatus.PENDING,
            ProcessingStatus.PROCESSING,
        }:
            skipped.append({"id": str(doc.id), "reason": "preparing"})
            continue

        status = compute_inbox_status(doc)
        if status == "needs_review" and not get_pending_folder_path(doc):
            in_inbox_folder = doc.folder is not None and doc.folder.kind == FolderKind.INBOX
            if in_inbox_folder:
                skipped.append({"id": str(doc.id), "reason": "needs_review"})
                continue

        try:
            async with session.begin_nested():
                pending_path = get_pending_folder_path(doc)
                if pending_path:
                    root = await folder_service.get_root(session, owner_id)
                    segments = _folder_segments(pending_path)
                    if not segments:
                        failed.append({"id": str(doc.id), "reason": "invalid_folder_path"})
                        continue
                    leaf = await folder_service.ensure_folder_path(
                        session, parent_id=root.id, segments=segments
                    )
                    doc.folder_id = leaf.id
                    set_pending_folder_path(doc, None)
                else:
                    # Must leave system Inbox folder
                    if doc.folder is not None and doc.folder.kind == FolderKind.INBOX:
                        skipped.append({"id": str(doc.id), "reason": "needs_folder"})
                        continue

                doc.inbox = False
                doc.needs_review = False
                doc.modified_date = datetime.now(UTC)
                await session.flush()

                if not doc.document_indexed:
                    await enqueue_job(
                        session,
                        job_type=JobType.INDEXING,
                        document_id=doc.id,
                        priority=priority,
                    )

                processed.append({"id": str(doc.id)})
        except Exception as exc:  # noqa: BLE001 — partial batch
            failed.append({"id": str(doc.id), "reason": str(exc)[:500]})

    return {"processed": processed, "skipped": skipped, "failed": failed}


async def purge_expired_trash(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID | None = None,
    retention_days: int | None = None,
    storage: StorageService | None = None,
) -> dict[str, int]:
    """Permanently delete trash items older than the retention window."""
    from datetime import timedelta

    from lesspaper_ngl.core.config import get_settings

    settings = get_settings()
    days = retention_days if retention_days is not None else settings.trash_retention_days
    cutoff = datetime.now(UTC) - timedelta(days=days)
    storage = storage or StorageService()

    expired_docs_stmt = select(Document.id).where(
        Document.is_trashed.is_(True),
        Document.trashed_at.is_not(None),
        Document.trashed_at < cutoff,
    )
    if owner_id is not None:
        expired_docs_stmt = expired_docs_stmt.where(Document.owner_id == owner_id)
    expired_docs = (await session.execute(expired_docs_stmt)).scalars().all()

    deleted_docs = 0
    for doc_id in expired_docs:
        try:
            await permanently_delete(
                session,
                doc_id,
                owner_id=owner_id,
                storage=storage,
            )
            deleted_docs += 1
        except Exception:
            # Continue purging remaining items
            continue

    # Delete empty trashed folders oldest-first (children before parents via depth)
    expired_folders_stmt = (
        select(Folder)
        .where(
            Folder.is_trashed.is_(True),
            Folder.kind == FolderKind.NORMAL,
            Folder.trashed_at.is_not(None),
            Folder.trashed_at < cutoff,
        )
        .order_by(Folder.trashed_at.asc())
    )
    if owner_id is not None:
        expired_folders_stmt = expired_folders_stmt.where(Folder.owner_id == owner_id)
    expired_folders = (await session.execute(expired_folders_stmt)).scalars().all()

    deleted_folders = 0
    # Multiple passes to delete leaves first
    remaining = list(expired_folders)
    for _ in range(len(remaining) + 1):
        if not remaining:
            break
        next_remaining: list[Folder] = []
        for folder in remaining:
            child_count = (
                await session.execute(
                    select(func.count()).select_from(Folder).where(Folder.parent_id == folder.id)
                )
            ).scalar_one()
            doc_count = (
                await session.execute(
                    select(func.count())
                    .select_from(Document)
                    .where(Document.folder_id == folder.id)
                )
            ).scalar_one()
            if child_count or doc_count:
                next_remaining.append(folder)
                continue
            await session.delete(folder)
            deleted_folders += 1
        await session.flush()
        if len(next_remaining) == len(remaining):
            break
        remaining = next_remaining

    return {
        "deleted_documents": deleted_docs,
        "deleted_folders": deleted_folders,
        "retention_days": days,
    }


async def empty_trash(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID | None = None,
    storage: StorageService | None = None,
) -> dict[str, int]:
    """Permanently delete all trashed documents and empty trashed folders now."""
    storage = storage or StorageService()
    doc_ids_stmt = select(Document.id).where(Document.is_trashed.is_(True))
    if owner_id is not None:
        doc_ids_stmt = doc_ids_stmt.where(Document.owner_id == owner_id)
    doc_ids = (await session.execute(doc_ids_stmt)).scalars().all()
    deleted_docs = 0
    for doc_id in doc_ids:
        await permanently_delete(
            session,
            doc_id,
            owner_id=owner_id,
            storage=storage,
        )
        deleted_docs += 1

    if owner_id is None:
        trashed_folders = (
            (
                await session.execute(
                    select(Folder).where(
                        Folder.is_trashed.is_(True),
                        Folder.kind == FolderKind.NORMAL,
                    )
                )
            )
            .scalars()
            .all()
        )
    else:
        trashed_folders = await folder_service.list_trashed_folders(session, owner_id)
    deleted_folders = 0
    remaining = list(trashed_folders)
    for _ in range(len(remaining) + 1):
        if not remaining:
            break
        next_remaining: list[Folder] = []
        for folder in remaining:
            try:
                await folder_service.permanently_delete_trashed_folder(
                    session,
                    folder.id,
                    owner_id=folder.owner_id,
                )
                deleted_folders += 1
            except Exception:
                next_remaining.append(folder)
        if len(next_remaining) == len(remaining):
            break
        remaining = next_remaining

    return {
        "deleted_documents": deleted_docs,
        "deleted_folders": deleted_folders,
    }


async def update_metadata(
    session: AsyncSession,
    document_id: uuid.UUID,
    data: dict,
    *,
    owner_id: uuid.UUID,
) -> Document:
    doc = await get_document(session, document_id, owner_id=owner_id)
    if "title" in data and data["title"] is not None:
        doc.title = data["title"].strip()
    if "folder_id" in data and data["folder_id"] is not None:
        await move_document(
            session,
            document_id,
            data["folder_id"],
            owner_id=owner_id,
        )
        doc = await get_document(session, document_id, owner_id=owner_id)
    if "document_type_id" in data:
        type_id = data["document_type_id"]
        if type_id is not None:
            document_type = await session.get(DocumentType, type_id)
            if document_type is None or document_type.owner_id != owner_id:
                raise NotFoundError("Document type not found")
        doc.document_type_id = type_id
    if "correspondent_id" in data:
        correspondent_id = data["correspondent_id"]
        if correspondent_id is not None:
            correspondent = await session.get(Correspondent, correspondent_id)
            if correspondent is None or correspondent.owner_id != owner_id:
                raise NotFoundError("Correspondent not found")
        doc.correspondent_id = correspondent_id
    if "created_date" in data:
        doc.created_date = data["created_date"]
    if "effective_date" in data:
        doc.effective_date = data["effective_date"]
    if "language" in data:
        doc.language = data["language"]
    if "notes" in data:
        doc.notes = data["notes"]
    if "custom_fields" in data and data["custom_fields"] is not None:
        doc.custom_fields = data["custom_fields"]
    if "pending_folder_path" in data:
        path = data["pending_folder_path"]
        if path is None or (isinstance(path, str) and not path.strip()):
            set_pending_folder_path(doc, None)
        elif isinstance(path, str):
            set_pending_folder_path(doc, path)
            # Choosing a new path clears a concrete folder assignment back to Inbox
            # only when still reviewing — keep current folder, Process creates path.
        else:
            raise ValidationError("pending_folder_path must be a string or null")
    if "inbox" in data and data["inbox"] is not None:
        doc.inbox = data["inbox"]
        if not doc.inbox:
            set_pending_folder_path(doc, None)
    if "is_archived" in data and data["is_archived"] is not None:
        doc.is_archived = data["is_archived"]
    if "needs_review" in data and data["needs_review"] is not None:
        doc.needs_review = data["needs_review"]
    if "tag_ids" in data and data["tag_ids"] is not None:
        tags = (
            (
                await session.execute(
                    select(Tag).where(
                        Tag.owner_id == owner_id,
                        Tag.id.in_(data["tag_ids"]),
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(tags) != len(set(data["tag_ids"])):
            raise NotFoundError("One or more tags not found")
        doc.tags = list(tags)
    doc.modified_date = datetime.now(UTC)
    await session.flush()
    return await get_document(session, doc.id, owner_id=owner_id)


async def list_documents(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    folder_id: uuid.UUID | None = None,
    include_descendants: bool = False,
    inbox: bool | None = None,
    inbox_status: InboxStatus | None = None,
    trashed: bool = False,
    unprocessed: bool | None = None,
    tag_ids: list[uuid.UUID] | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 50,
    sort: str = "added_date",
    order: str = "desc",
) -> tuple[list[Document], int]:
    stmt: Select = (
        select(Document).options(*_document_options()).where(Document.owner_id == owner_id)
    )
    count_stmt = select(func.count(Document.id)).where(Document.owner_id == owner_id)

    if trashed:
        stmt = stmt.where(Document.is_trashed.is_(True))
        count_stmt = count_stmt.where(Document.is_trashed.is_(True))
    else:
        stmt = stmt.where(Document.is_trashed.is_(False))
        count_stmt = count_stmt.where(Document.is_trashed.is_(False))

    if unprocessed is True:
        # Documents still in the ingestion → indexing lifecycle (not RAG-ready).
        unprocessed_filt = or_(
            Document.inbox.is_(True),
            Document.needs_review.is_(True),
            Document.document_indexed.is_(False),
            Document.processing_status.in_(
                [
                    ProcessingStatus.PENDING,
                    ProcessingStatus.PROCESSING,
                    ProcessingStatus.FAILED,
                    ProcessingStatus.PARTIAL,
                ]
            ),
        )
        stmt = stmt.where(unprocessed_filt)
        count_stmt = count_stmt.where(unprocessed_filt)
    elif inbox is True:
        stmt = stmt.where(Document.inbox.is_(True))
        count_stmt = count_stmt.where(Document.inbox.is_(True))
    elif inbox is False:
        stmt = stmt.where(Document.inbox.is_(False))
        count_stmt = count_stmt.where(Document.inbox.is_(False))

    if folder_id is not None:
        await folder_service.get_folder(session, folder_id, owner_id=owner_id)
        if include_descendants:
            ids = await folder_service.descendant_ids(
                session,
                folder_id,
                owner_id=owner_id,
            )
            stmt = stmt.where(Document.folder_id.in_(ids))
            count_stmt = count_stmt.where(Document.folder_id.in_(ids))
        else:
            stmt = stmt.where(Document.folder_id == folder_id)
            count_stmt = count_stmt.where(Document.folder_id == folder_id)

    if tag_ids:
        for tag_id in tag_ids:
            stmt = stmt.where(Document.tags.any(Tag.id == tag_id))
            count_stmt = count_stmt.where(Document.tags.any(Tag.id == tag_id))

    if q:
        pattern = f"%{q}%"
        filt = or_(
            Document.title.ilike(pattern),
            Document.original_filename.ilike(pattern),
            Document.notes.ilike(pattern),
        )
        stmt = stmt.where(filt)
        count_stmt = count_stmt.where(filt)

    sort_map = {
        "added_date": Document.added_date,
        "title": Document.title,
        "modified_date": Document.modified_date,
        "created_date": Document.created_date,
    }
    sort_key = sort if sort in sort_map else "added_date"
    sort_col = sort_map[sort_key]
    ascending = order.lower() == "asc"
    order_clauses = [sort_col.asc() if ascending else sort_col.desc()]
    if sort_key == "added_date":
        order_clauses.append(
            Document.created_at.asc() if ascending else Document.created_at.desc()
        )
    stmt = stmt.order_by(*order_clauses)

    # inbox_status is derived — filter in Python after fetch when requested.
    # For status tabs, fetch a larger page then filter (Inbox queues stay small).
    if inbox_status is not None:
        # Load all matching inbox candidates (capped) then filter + paginate
        base_items = list((await session.execute(stmt.limit(2000))).scalars().unique().all())
        filtered = [d for d in base_items if compute_inbox_status(d) == inbox_status]
        total = len(filtered)
        start = (page - 1) * page_size
        items = filtered[start : start + page_size]
        return items, total

    total = (await session.execute(count_stmt)).scalar_one()
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    items = list((await session.execute(stmt)).scalars().unique().all())
    return items, total


def _purge_after(trashed_at: datetime | None) -> datetime | None:
    if trashed_at is None:
        return None
    from datetime import timedelta

    from lesspaper_ngl.core.config import get_settings

    return trashed_at + timedelta(days=get_settings().trash_retention_days)


def document_to_dict(doc: Document) -> dict:
    return {
        "id": doc.id,
        "title": doc.title,
        "original_filename": doc.original_filename,
        "mime_type": doc.mime_type,
        "file_size": doc.file_size,
        "page_count": doc.page_count,
        "language": doc.language,
        "notes": doc.notes,
        "archive_serial": doc.archive_serial,
        "folder_id": doc.folder_id,
        "folder_path": doc.folder.path_cache if doc.folder else None,
        "document_type_id": doc.document_type_id,
        "document_type_name": doc.document_type.name if doc.document_type else None,
        "correspondent_id": doc.correspondent_id,
        "correspondent_name": doc.correspondent.name if doc.correspondent else None,
        "tags": [{"id": t.id, "name": t.name, "color": t.color} for t in doc.tags],
        "created_date": doc.created_date,
        "effective_date": doc.effective_date,
        "added_date": doc.added_date,
        "modified_date": doc.modified_date,
        "indexed_at": doc.indexed_at,
        "processing_status": doc.processing_status.value,
        "ocr_completed": doc.ocr_completed,
        "ocr_pages_done": doc.ocr_pages_done,
        "ocr_pages_total": doc.ocr_pages_total,
        "text_extracted": doc.text_extracted,
        "document_indexed": doc.document_indexed,
        "has_embeddings": doc.has_embeddings,
        "chunks_total": doc.chunks_total,
        "chunks_embedded": doc.chunks_embedded,
        "chunks_failed": doc.chunks_failed,
        "embedding_error": doc.embedding_error,
        "embedding_started_at": doc.embedding_started_at,
        "embedding_finished_at": doc.embedding_finished_at,
        "processing_error": doc.processing_error,
        "is_archived": doc.is_archived,
        "is_trashed": doc.is_trashed,
        "trashed_at": doc.trashed_at,
        "trashed_from_folder_id": doc.trashed_from_folder_id,
        "purge_after": _purge_after(doc.trashed_at),
        "inbox": doc.inbox,
        "needs_review": doc.needs_review,
        "inbox_status": compute_inbox_status(doc),
        "pending_folder_path": get_pending_folder_path(doc),
        "custom_fields": doc.custom_fields or {},
        "ai_summary": doc.ai_summary,
        "ai_summary_meta": doc.ai_summary_meta,
        "has_thumbnail": bool(doc.thumbnail_key),
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
    }
