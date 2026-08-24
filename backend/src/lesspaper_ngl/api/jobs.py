"""Background job endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.api.schemas import JobOut
from lesspaper_ngl.auth.deps import CurrentUser, SafeSession
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.models import JobStatus
from lesspaper_ngl.services import jobs as job_service

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _job_out(job) -> JobOut:
    return JobOut(
        id=job.id,
        job_type=job.job_type.value,
        status=job.status.value,
        document_id=job.document_id,
        priority=job.priority,
        retry_count=job.retry_count,
        error=job.error,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


@router.get("", response_model=list[JobOut])
async def list_jobs(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    status: JobStatus | None = None,
    document_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[JobOut]:
    jobs = await job_service.list_jobs(
        db,
        status=status,
        document_id=document_id,
        owner_id=None if _user.is_admin else _user.id,
        limit=limit,
    )
    return [_job_out(j) for j in jobs]


@router.get("/{job_id}", response_model=JobOut)
async def get_job(
    job_id: uuid.UUID,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobOut:
    job = await job_service.get_job(db, job_id, owner_id=None if _user.is_admin else _user.id)
    return _job_out(job)


@router.post("/{job_id}/cancel", response_model=JobOut)
async def cancel_job(
    job_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> JobOut:
    job = await job_service.cancel_job(db, job_id, owner_id=None if _user.is_admin else _user.id)
    return _job_out(job)
