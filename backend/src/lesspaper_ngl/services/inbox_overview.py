"""Inbox overview metrics and activity (read-only over existing Document rows)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.models import Document, ProcessingStatus
from lesspaper_ngl.services import library_stats as library_stats_service
from lesspaper_ngl.services.documents import (
    _document_options,
    compute_inbox_status,
    document_to_dict,
)

ActivityStatus = Literal["queued", "processing", "processed", "needs_review", "failed"]
ActivityTab = Literal["recent", "processed", "failed"]
RangeDays = Literal[7, 30]


def range_start(range_days: int, *, now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    start = current.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return start - timedelta(days=range_days - 1)


def activity_status_for(doc: Document) -> ActivityStatus:
    if not doc.inbox:
        return "processed"
    status = compute_inbox_status(doc)
    if status == "failed":
        return "failed"
    if status == "ready":
        return "processed"
    if status == "needs_review":
        return "needs_review"
    if status == "preparing":
        if doc.processing_status == ProcessingStatus.PROCESSING:
            return "processing"
        return "queued"
    return "queued"


async def get_overview_metrics(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    range_days: RangeDays,
) -> dict:
    _ = range_days  # retained for activity listing compatibility only
    activity = await library_stats_service.get_activity(session, owner_id)

    processing = (
        await session.execute(
            select(func.count(Document.id)).where(
                Document.owner_id == owner_id,
                Document.is_trashed.is_(False),
                Document.inbox.is_(True),
                Document.processing_status.in_(
                    [ProcessingStatus.PENDING, ProcessingStatus.PROCESSING]
                ),
            )
        )
    ).scalar_one()

    processed = activity["successful_processing"]
    failed = activity["failed_documents"]
    total_ingested = activity["documents_ingested"]
    terminal = int(processed) + int(failed)
    success_rate = (int(processed) / terminal * 100.0) if terminal else None

    return {
        "range_days": int(range_days),
        "processed": int(processed),
        "failed": int(failed),
        "processing": int(processing),
        "total_ingested": int(total_ingested),
        "success_rate": success_rate,
    }


async def list_activity(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    range_days: RangeDays,
    tab: ActivityTab = "recent",
    q: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[dict], int]:
    start = range_start(int(range_days))
    stmt = (
        select(Document)
        .options(*_document_options())
        .where(
            Document.owner_id == owner_id,
            Document.is_trashed.is_(False),
            or_(
                Document.inbox.is_(True),
                and_(Document.inbox.is_(False), Document.added_date >= start),
            ),
        )
        .order_by(Document.added_date.desc())
    )

    if q:
        pattern = f"%{q}%"
        stmt = stmt.where(
            or_(
                Document.title.ilike(pattern),
                Document.original_filename.ilike(pattern),
                Document.notes.ilike(pattern),
            )
        )

    # Activity status is derived — filter in Python after fetch (queues stay small).
    candidates = list((await session.execute(stmt.limit(2000))).scalars().unique().all())
    items: list[tuple[Document, ActivityStatus]] = []
    for doc in candidates:
        status = activity_status_for(doc)
        if tab == "processed" and status not in {"processed", "needs_review"}:
            continue
        if tab == "failed" and status != "failed":
            continue
        items.append((doc, status))

    total = len(items)
    start_idx = (page - 1) * page_size
    page_items = items[start_idx : start_idx + page_size]
    return [
        {**document_to_dict(doc), "activity_status": status} for doc, status in page_items
    ], total
