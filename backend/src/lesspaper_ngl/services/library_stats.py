"""Owner-scoped increment-only library activity counters and live aggregates."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.models import (
    Document,
    DocumentTag,
    Folder,
    FolderKind,
    LibraryActivityCounters,
    ProcessingStatus,
    Tag,
)

COUNTER_FIELDS = (
    "documents_ingested",
    "bytes_ingested",
    "pages_processed",
    "successful_processing",
    "ocr_pages",
    "failed_documents",
    "duplicates_rejected",
    "purged_documents",
)


async def get_or_create_counters(
    session: AsyncSession,
    owner_id: uuid.UUID,
) -> LibraryActivityCounters:
    row = await session.get(LibraryActivityCounters, owner_id)
    if row is not None:
        return row
    row = LibraryActivityCounters(owner_id=owner_id)
    session.add(row)
    await session.flush()
    return row


async def bump_counters(
    session: AsyncSession,
    owner_id: uuid.UUID,
    **deltas: int,
) -> None:
    if not deltas:
        return
    unknown = set(deltas) - set(COUNTER_FIELDS)
    if unknown:
        raise ValueError(f"Unknown counter fields: {unknown}")
    filtered = {k: v for k, v in deltas.items() if v}
    if not filtered:
        return
    await get_or_create_counters(session, owner_id)
    values = {field: LibraryActivityCounters.__table__.c[field] + filtered[field] for field in filtered}
    await session.execute(
        update(LibraryActivityCounters)
        .where(LibraryActivityCounters.owner_id == owner_id)
        .values(**values)
    )


async def reset_counters(session: AsyncSession, owner_id: uuid.UUID) -> LibraryActivityCounters:
    row = await get_or_create_counters(session, owner_id)
    for field in COUNTER_FIELDS:
        setattr(row, field, 0)
    row.reset_at = datetime.now(UTC)
    await session.flush()
    return row


def _format_since(reset_at: datetime) -> str:
    dt = reset_at.astimezone(UTC)
    return dt.strftime("%d %b %Y")


async def get_activity(session: AsyncSession, owner_id: uuid.UUID) -> dict[str, Any]:
    row = await get_or_create_counters(session, owner_id)
    return {
        "documents_ingested": int(row.documents_ingested),
        "bytes_ingested": int(row.bytes_ingested),
        "pages_processed": int(row.pages_processed),
        "successful_processing": int(row.successful_processing),
        "ocr_pages": int(row.ocr_pages),
        "failed_documents": int(row.failed_documents),
        "duplicates_rejected": int(row.duplicates_rejected),
        "purged_documents": int(row.purged_documents),
        "reset_at": row.reset_at,
        "since_label": _format_since(row.reset_at),
    }


def _owner_active(owner_id: uuid.UUID) -> list:
    return [Document.owner_id == owner_id, Document.is_trashed.is_(False)]


def _unprocessed_filter():
    return or_(
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


def _mime_label(mime: str) -> tuple[str, str]:
    mime_lower = (mime or "").lower()
    mapping = {
        "application/pdf": ("PDF", "#EF4444"),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ("DOCX", "#2563EB"),
        "application/msword": ("DOCX", "#2563EB"),
        "image/jpeg": ("JPG", "#9333EA"),
        "image/jpg": ("JPG", "#9333EA"),
        "image/png": ("PNG", "#059669"),
        "text/plain": ("TXT", "#64748B"),
        "text/markdown": ("Markdown", "#64748B"),
    }
    if mime_lower in mapping:
        return mapping[mime_lower]
    if mime_lower.startswith("image/"):
        ext = mime_lower.split("/", 1)[-1].upper()
        return ext, "#64748B"
    if mime_lower:
        return mime_lower.split("/")[-1].upper(), "#64748B"
    return "Unknown", "#64748B"


async def get_snapshot(session: AsyncSession, owner_id: uuid.UUID) -> dict[str, int]:
    owner_ok = _owner_active(owner_id)
    current_documents = (
        await session.execute(select(func.count(Document.id)).where(*owner_ok))
    ).scalar_one()
    library_size_bytes = (
        await session.execute(select(func.coalesce(func.sum(Document.file_size), 0)).where(*owner_ok))
    ).scalar_one()
    folders = (
        await session.execute(
            select(func.count(Folder.id)).where(
                Folder.owner_id == owner_id,
                Folder.kind == FolderKind.NORMAL,
            )
        )
    ).scalar_one()
    tags = (
        await session.execute(select(func.count(Tag.id)).where(Tag.owner_id == owner_id))
    ).scalar_one()
    archived = (
        await session.execute(
            select(func.count(Document.id)).where(*owner_ok, Document.is_archived.is_(True))
        )
    ).scalar_one()
    unprocessed = (
        await session.execute(
            select(func.count(Document.id)).where(*owner_ok, _unprocessed_filter())
        )
    ).scalar_one()
    return {
        "current_documents": int(current_documents),
        "library_size_bytes": int(library_size_bytes),
        "folders": int(folders),
        "tags": int(tags),
        "archived": int(archived),
        "unprocessed": int(unprocessed),
    }


async def get_file_types(
    session: AsyncSession,
    owner_id: uuid.UUID,
) -> dict[str, Any]:
    owner_ok = _owner_active(owner_id)
    rows = (
        await session.execute(
            select(
                Document.mime_type,
                func.count(Document.id),
                func.coalesce(func.sum(Document.file_size), 0),
            )
            .where(*owner_ok)
            .group_by(Document.mime_type)
            .order_by(func.count(Document.id).desc())
        )
    ).all()
    total_docs = sum(int(r[1]) for r in rows)
    total_bytes = sum(int(r[2]) for r in rows)
    items: list[dict[str, Any]] = []
    for mime, count, size in rows:
        label, colour = _mime_label(mime or "")
        pct = (int(count) / total_docs * 100.0) if total_docs else 0.0
        items.append(
            {
                "type": label,
                "mime_type": mime or "",
                "documents": int(count),
                "size_bytes": int(size),
                "percentage": round(pct, 1),
                "usage_percent": max(1, round(pct)) if pct > 0 else 0,
                "icon_colour": colour,
            }
        )
    total_types = len(items)
    return {
        "items": items,
        "total_types": total_types,
        "total_documents": total_docs,
        "total_bytes": total_bytes,
    }


async def get_health(session: AsyncSession, owner_id: uuid.UUID) -> dict[str, int]:
    owner_ok = _owner_active(owner_id)
    activity = await get_activity(session, owner_id)
    needs_processing = (
        await session.execute(
            select(func.count(Document.id)).where(*owner_ok, _unprocessed_filter())
        )
    ).scalar_one()
    failed = (
        await session.execute(
            select(func.count(Document.id)).where(
                *owner_ok,
                Document.processing_status == ProcessingStatus.FAILED,
            )
        )
    ).scalar_one()
    missing_text = (
        await session.execute(
            select(func.count(Document.id)).where(
                *owner_ok,
                Document.text_extracted.is_(False),
            )
        )
    ).scalar_one()
    unused_tags = (
        await session.execute(
            select(func.count(Tag.id)).where(
                Tag.owner_id == owner_id,
                ~select(DocumentTag.document_id)
                .join(Document, Document.id == DocumentTag.document_id)
                .where(
                    DocumentTag.tag_id == Tag.id,
                    Document.owner_id == owner_id,
                    Document.is_trashed.is_(False),
                )
                .exists(),
            )
        )
    ).scalar_one()
    empty_folders = (
        await session.execute(
            select(func.count(Folder.id)).where(
                Folder.owner_id == owner_id,
                Folder.kind == FolderKind.NORMAL,
                ~select(Document.id)
                .where(
                    Document.folder_id == Folder.id,
                    Document.owner_id == owner_id,
                    Document.is_trashed.is_(False),
                )
                .exists(),
            )
        )
    ).scalar_one()
    return {
        "needs_processing": int(needs_processing),
        "failed_documents": int(failed),
        "missing_text": int(missing_text),
        "unused_tags": int(unused_tags),
        "duplicate_content": int(activity["duplicates_rejected"]),
        "empty_folders": int(empty_folders),
    }


async def list_tags_with_counts(session: AsyncSession, owner_id: uuid.UUID) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(Tag, func.count(Document.id))
        .outerjoin(DocumentTag, DocumentTag.tag_id == Tag.id)
        .outerjoin(
            Document,
            and_(
                Document.id == DocumentTag.document_id,
                Document.owner_id == owner_id,
                Document.is_trashed.is_(False),
            ),
        )
        .where(Tag.owner_id == owner_id)
        .group_by(Tag.id)
        .order_by(Tag.name)
    )
    return [
        {
            "id": tag.id,
            "name": tag.name,
            "color": tag.color,
            "slug": tag.slug,
            "document_count": int(count),
        }
        for tag, count in rows.all()
    ]


async def get_overview(session: AsyncSession, owner_id: uuid.UUID) -> dict[str, Any]:
    return {
        "activity": await get_activity(session, owner_id),
        "snapshot": await get_snapshot(session, owner_id),
        "file_types": await get_file_types(session, owner_id),
        "health": await get_health(session, owner_id),
        "tags": await list_tags_with_counts(session, owner_id),
    }
