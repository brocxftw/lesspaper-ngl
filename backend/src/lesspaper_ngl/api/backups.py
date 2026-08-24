"""Admin backup and restore API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.api.schemas import (
    BackupConfirmIn,
    BackupInspectOut,
    BackupRecordOut,
    BackupRepositoryHealthOut,
    BackupRestoreStatusOut,
    BackupSettingsOut,
    BackupSettingsUpdate,
)
from lesspaper_ngl.auth.deps import AdminUser, SafeSession
from lesspaper_ngl.backup.paths import bundle_path, check_repository_health
from lesspaper_ngl.backup.restore import get_restore_status, start_restore_background
from lesspaper_ngl.backup.schedule import next_run_after
from lesspaper_ngl.backup.verify import inspect_bundle_file
from lesspaper_ngl.core.exceptions import NotFoundError, ValidationError
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.models import (
    BackupRecord,
    BackupScheduleType,
    InstanceState,
    JobType,
)
from lesspaper_ngl.services import backup as backup_service
from lesspaper_ngl.services import instance_state as instance_state_service
from lesspaper_ngl.services.jobs import enqueue_job

router = APIRouter(prefix="/api/backups", tags=["backups"])


def _record_out(record: BackupRecord) -> BackupRecordOut:
    return BackupRecordOut(
        id=record.id,
        filename=record.filename,
        relative_key=record.relative_key,
        created_at=record.created_at,
        completed_at=record.completed_at,
        size_bytes=record.size_bytes,
        document_count=record.document_count,
        folium_version=record.folium_version,
        schema_version=record.schema_version,
        format_version=record.format_version,
        status=record.status.value if hasattr(record.status, "value") else str(record.status),
        verification_status=(
            record.verification_status.value
            if hasattr(record.verification_status, "value")
            else str(record.verification_status)
        ),
        verified_at=record.verified_at,
        error_message=record.error_message,
        progress_stage=record.progress_stage,
    )


@router.get("/settings", response_model=BackupSettingsOut)
async def get_settings(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BackupSettingsOut:
    policy = await backup_service.get_or_create_settings(db)
    health = check_repository_health(policy.repository_subdir)
    return BackupSettingsOut(
        enabled=policy.enabled,
        schedule_type=policy.schedule_type.value,
        backup_time=policy.backup_time,
        weekday=policy.weekday,
        interval_hours=policy.interval_hours,
        repository_subdir=policy.repository_subdir,
        retention_count=policy.retention_count,
        verify_after_backup=policy.verify_after_backup,
        last_success_at=policy.last_success_at,
        next_run_at=policy.next_run_at,
        repository=BackupRepositoryHealthOut(
            configured=health.configured,
            exists=health.exists,
            readable=health.readable,
            writable=health.writable,
            path=health.path,
            free_bytes=health.free_bytes,
            message=health.message,
        ),
    )


@router.patch("/settings", response_model=BackupSettingsOut)
async def update_settings(
    body: BackupSettingsUpdate,
    _admin: AdminUser,
    _sess: SafeSession,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BackupSettingsOut:
    policy = await backup_service.get_or_create_settings(db)
    if body.enabled is not None:
        policy.enabled = body.enabled
    if body.schedule_type is not None:
        try:
            policy.schedule_type = BackupScheduleType(body.schedule_type)
        except ValueError as exc:
            raise ValidationError("Invalid backup schedule type") from exc
    if body.backup_time is not None:
        parts = body.backup_time.split(":")
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValidationError("backup_time must be HH:MM")
        hour, minute = int(parts[0]), int(parts[1])
        if hour > 23 or minute > 59:
            raise ValidationError("backup_time must be HH:MM")
        policy.backup_time = f"{hour:02d}:{minute:02d}"
    if body.weekday is not None:
        policy.weekday = body.weekday
    if body.interval_hours is not None:
        policy.interval_hours = body.interval_hours
    if body.repository_subdir is not None:
        sub = body.repository_subdir.strip().strip("/")
        check_repository_health(sub)  # validates path safety
        policy.repository_subdir = sub
    if body.retention_count is not None:
        policy.retention_count = body.retention_count
    if body.verify_after_backup is not None:
        policy.verify_after_backup = body.verify_after_backup
    if policy.enabled:
        policy.next_run_at = next_run_after(policy)
    else:
        policy.next_run_at = None
    await db.flush()
    return await get_settings(_admin, db)


@router.get("/restore/status", response_model=BackupRestoreStatusOut)
async def restore_status(_admin: AdminUser) -> BackupRestoreStatusOut:
    state = get_restore_status()
    return BackupRestoreStatusOut(**state.to_dict())


@router.get("", response_model=list[BackupRecordOut])
async def list_backups(
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[BackupRecordOut]:
    records = await backup_service.discover_backups(db)
    return [_record_out(r) for r in records]


@router.post("", response_model=BackupRecordOut, status_code=status.HTTP_202_ACCEPTED)
async def create_backup(
    _admin: AdminUser,
    _sess: SafeSession,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BackupRecordOut:
    state = await instance_state_service.get_instance_state(db)
    if state != InstanceState.READY:
        raise HTTPException(status_code=409, detail="Backups are unavailable until the instance is ready")
    if await backup_service.has_active_backup_job(db):
        raise HTTPException(status_code=409, detail="A backup is already queued or running")
    try:
        record = await backup_service.create_backup_record(db, manual=True)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _record_out(record)


@router.post("/{record_id}/verify", response_model=BackupRecordOut)
async def verify_backup(
    record_id: uuid.UUID,
    _admin: AdminUser,
    _sess: SafeSession,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BackupRecordOut:
    record = await db.get(BackupRecord, record_id)
    if record is None:
        raise NotFoundError("Backup not found")
    if await backup_service.has_active_backup_job(db):
        raise HTTPException(status_code=409, detail="A backup is already queued or running")
    job = await enqueue_job(
        db,
        job_type=JobType.BACKUP_VERIFY,
        document_id=None,
        priority=60,
        payload={"backup_record_id": str(record.id)},
        max_retries=0,
    )
    record.job_id = job.id
    await db.flush()
    return _record_out(record)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backup(
    record_id: uuid.UUID,
    body: BackupConfirmIn,
    _admin: AdminUser,
    _sess: SafeSession,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    if not body.confirm:
        raise ValidationError("Deletion requires confirm=true")
    record = await db.get(BackupRecord, record_id)
    if record is None:
        raise NotFoundError("Backup not found")
    policy = await backup_service.get_or_create_settings(db)
    try:
        path = bundle_path(record.filename, policy.repository_subdir)
        if path.is_file():
            path.unlink()
    except ValidationError:
        pass
    await db.delete(record)


@router.get("/{record_id}/inspect", response_model=BackupInspectOut)
async def inspect_backup(
    record_id: uuid.UUID,
    _admin: AdminUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BackupInspectOut:
    record = await db.get(BackupRecord, record_id)
    if record is None:
        raise NotFoundError("Backup not found")
    policy = await backup_service.get_or_create_settings(db)
    path = bundle_path(record.filename, policy.repository_subdir)
    result = inspect_bundle_file(path, verify_checksums_flag=True)
    return BackupInspectOut(
        manifest=result.manifest.to_dict(),
        verification_status=result.verification_status.value,
        compatible=result.compatible,
        messages=result.messages,
    )


@router.post("/{record_id}/restore", status_code=status.HTTP_202_ACCEPTED)
async def restore_backup(
    record_id: uuid.UUID,
    body: BackupConfirmIn,
    _admin: AdminUser,
    _sess: SafeSession,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> BackupRestoreStatusOut:
    if not body.confirm:
        raise ValidationError("Restore requires confirm=true")
    if await backup_service.has_active_backup_job(db):
        raise HTTPException(status_code=409, detail="Cannot restore while a backup is running")
    record = await db.get(BackupRecord, record_id)
    if record is None:
        raise NotFoundError("Backup not found")
    policy = await backup_service.get_or_create_settings(db)
    status_obj = get_restore_status()
    if status_obj.active:
        raise HTTPException(status_code=409, detail="A restore is already in progress")
    await start_restore_background(
        record.filename, subdir=policy.repository_subdir, safety_dump=True, background_tasks=background_tasks
    )
    return BackupRestoreStatusOut(**get_restore_status().to_dict())
