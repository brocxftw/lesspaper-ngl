"""Background job queue backed by PostgreSQL."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, exists, not_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.core.exceptions import NotFoundError
from lesspaper_ngl.models import Document, Job, JobStatus, JobType, ProcessingStatus

PREPARING_STATUSES = frozenset(
    {ProcessingStatus.PENDING, ProcessingStatus.PROCESSING}
)

INBOX_PREFLIGHT_JOB_TYPES = frozenset(
    {
        JobType.TEXT_EXTRACTION,
        JobType.OCR,
        JobType.THUMBNAIL,
        JobType.METADATA_SUGGESTION,
    }
)


async def enqueue_job(
    session: AsyncSession,
    *,
    job_type: JobType,
    document_id: uuid.UUID | None = None,
    priority: int = 100,
    payload: dict[str, Any] | None = None,
    max_retries: int = 3,
) -> Job:
    job = Job(
        job_type=job_type,
        status=JobStatus.QUEUED,
        document_id=document_id,
        priority=priority,
        payload=payload or {},
        max_retries=max_retries,
    )
    session.add(job)
    await session.flush()
    return job


async def _active_inbox_preflight_document_id(
    session: AsyncSession,
) -> uuid.UUID | None:
    """Oldest inbox document that currently owns the preflight pipeline.

    A running preflight job pins that document. Otherwise the oldest inbox
    document with a queued preflight job is selected.
    """
    inbox_preflight = (
        select(Document.id)
        .join(Job, Job.document_id == Document.id)
        .where(
            Document.inbox.is_(True),
            Document.is_trashed.is_(False),
            Document.processing_status.in_(PREPARING_STATUSES),
            Job.job_type.in_(INBOX_PREFLIGHT_JOB_TYPES),
        )
    )
    running = (
        await session.execute(
            inbox_preflight.where(Job.status == JobStatus.RUNNING)
            .order_by(Document.added_date.asc(), Document.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if running is not None:
        return running
    now = datetime.now(UTC)
    return (
        await session.execute(
            inbox_preflight.where(
                Job.status == JobStatus.QUEUED,
                or_(Job.available_at.is_(None), Job.available_at <= now),
            )
            .order_by(Document.added_date.asc(), Document.created_at.asc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def claim_next(session: AsyncSession, worker_id: str) -> Job | None:
    """Claim the highest-priority queued job using SKIP LOCKED.

    Skips jobs whose document is trashed so deleted batches cannot starve the queue.
    Inbox preflight jobs (extract/OCR/thumbnail/suggestions) are claimed for
    only one still-preparing document at a time, oldest first. Ready inbox
    docs (e.g. manual suggestion retries) keep normal claim order.
    """
    now = datetime.now(UTC)
    trashed_document = (
        select(Document.id)
        .where(
            Document.id == Job.document_id,
            Document.is_trashed.is_(True),
        )
        .exists()
    )
    inbox_preflight_job = and_(
        Job.job_type.in_(INBOX_PREFLIGHT_JOB_TYPES),
        exists().where(
            Document.id == Job.document_id,
            Document.inbox.is_(True),
            Document.is_trashed.is_(False),
            Document.processing_status.in_(PREPARING_STATUSES),
        ),
    )
    allowed_inbox_id = await _active_inbox_preflight_document_id(session)
    inbox_gate = (
        or_(not_(inbox_preflight_job), Job.document_id == allowed_inbox_id)
        if allowed_inbox_id is not None
        else not_(inbox_preflight_job)
    )
    stmt = (
        select(Job)
        .where(
            Job.status == JobStatus.QUEUED,
            or_(Job.available_at.is_(None), Job.available_at <= now),
            ~trashed_document,
            inbox_gate,
        )
        .order_by(Job.priority.asc(), Job.created_at.asc())
        .limit(1)
        .with_for_update(of=Job, skip_locked=True)
    )
    result = await session.execute(stmt)
    job = result.scalar_one_or_none()
    if job is None:
        return None
    job.status = JobStatus.RUNNING
    job.locked_by = worker_id
    job.locked_at = now
    job.started_at = now
    job.available_at = None
    await session.flush()
    return job


async def complete_job(
    session: AsyncSession, job_id: uuid.UUID, result: dict[str, Any] | None = None
) -> Job:
    job = await session.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found")
    # Preserve cooperative cancellation if the job was cancelled mid-run.
    if job.status == JobStatus.CANCELLED:
        job.result = result
        await session.flush()
        return job
    job.status = JobStatus.COMPLETED
    job.result = result
    job.error = None
    job.available_at = None
    job.completed_at = datetime.now(UTC)
    job.locked_by = None
    await session.flush()
    return job


async def touch_job_lock(session: AsyncSession, job_id: uuid.UUID) -> None:
    """Refresh locked_at so long-running jobs are not reclaimed as stale."""
    await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.RUNNING)
        .values(locked_at=datetime.now(UTC))
    )


async def fail_job(
    session: AsyncSession,
    job_id: uuid.UUID,
    error: str,
    *,
    delay_seconds: float | None = None,
) -> Job:
    job = await session.get(Job, job_id)
    if job is None:
        raise NotFoundError("Job not found")
    job.retry_count += 1
    job.error = error
    if job.retry_count <= job.max_retries:
        job.status = JobStatus.QUEUED
        job.locked_by = None
        job.locked_at = None
        job.started_at = None
        # Lower priority slightly on retry
        job.priority = min(job.priority + 5, 1000)
        if delay_seconds is not None and delay_seconds > 0:
            job.available_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        else:
            job.available_at = None
    else:
        job.status = JobStatus.FAILED
        job.completed_at = datetime.now(UTC)
        job.locked_by = None
        job.available_at = None
    await session.flush()
    return job


async def cancel_job(
    session: AsyncSession, job_id: uuid.UUID, *, owner_id: uuid.UUID | None = None
) -> Job:
    job = await get_job(session, job_id, owner_id=owner_id)
    if job.status in {JobStatus.COMPLETED, JobStatus.CANCELLED}:
        return job
    job.status = JobStatus.CANCELLED
    job.completed_at = datetime.now(UTC)
    job.locked_by = None
    job.available_at = None
    await session.flush()
    return job


async def get_job(
    session: AsyncSession, job_id: uuid.UUID, *, owner_id: uuid.UUID | None = None
) -> Job:
    if owner_id is None:
        job = await session.get(Job, job_id)
    else:
        job = (
            await session.execute(
                select(Job)
                .join(Document, Document.id == Job.document_id)
                .where(Job.id == job_id, Document.owner_id == owner_id)
            )
        ).scalar_one_or_none()
    if job is None:
        raise NotFoundError("Job not found")
    return job


async def list_jobs(
    session: AsyncSession,
    *,
    status: JobStatus | None = None,
    document_id: uuid.UUID | None = None,
    owner_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[Job]:
    stmt = select(Job).order_by(Job.created_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(Job.status == status)
    if document_id is not None:
        stmt = stmt.where(Job.document_id == document_id)
    if owner_id is not None:
        stmt = stmt.join(Document, Document.id == Job.document_id).where(
            Document.owner_id == owner_id
        )
    return list((await session.execute(stmt)).scalars().all())


async def requeue_stale_running(session: AsyncSession, *, older_than_seconds: int = 600) -> int:
    """Requeue RUNNING jobs whose lock heartbeat is older than ``older_than_seconds``."""
    cutoff = datetime.now(UTC).timestamp() - older_than_seconds
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=UTC)
    result = await session.execute(
        update(Job)
        .where(Job.status == JobStatus.RUNNING, Job.locked_at < cutoff_dt)
        .values(
            status=JobStatus.QUEUED,
            locked_by=None,
            locked_at=None,
            started_at=None,
            available_at=None,
        )
    )
    return result.rowcount or 0


async def requeue_all_running(session: AsyncSession) -> int:
    """Requeue every RUNNING job (worker startup after crash/redeploy)."""
    result = await session.execute(
        update(Job)
        .where(Job.status == JobStatus.RUNNING)
        .values(
            status=JobStatus.QUEUED,
            locked_by=None,
            locked_at=None,
            started_at=None,
            available_at=None,
        )
    )
    return result.rowcount or 0


async def cancel_jobs_for_trashed_documents(session: AsyncSession) -> int:
    """Cancel queued/running jobs for trashed documents (they must not occupy workers)."""
    now = datetime.now(UTC)
    trashed_ids = select(Document.id).where(Document.is_trashed.is_(True))
    result = await session.execute(
        update(Job)
        .where(
            Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
            Job.document_id.in_(trashed_ids),
        )
        .values(
            status=JobStatus.CANCELLED,
            locked_by=None,
            locked_at=None,
            available_at=None,
            completed_at=now,
            error="Cancelled: document is trashed",
        )
    )
    return result.rowcount or 0
