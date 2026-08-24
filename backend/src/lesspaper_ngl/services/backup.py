"""Backup orchestration service."""

from __future__ import annotations

import shutil
import socket
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl import __version__
from lesspaper_ngl.backup.bundle import (
    cleanup_staging,
    cleanup_temp_glob,
    copy_file,
    create_bundle_archive,
    verify_checksums,
    write_checksums,
    write_manifest,
)
from lesspaper_ngl.backup.dump import run_pg_dump, validate_dump_readable
from lesspaper_ngl.backup.manifest import (
    BUNDLE_EXTENSION,
    CHECKSUM_ALGORITHM,
    BackupManifest,
    bundle_filename,
)
from lesspaper_ngl.backup.paths import (
    bundle_path,
    check_repository_health,
    relative_key,
    repository_path,
)
from lesspaper_ngl.backup.retention import apply_retention
from lesspaper_ngl.backup.verify import _current_schema_head as _schema_head
from lesspaper_ngl.backup.verify import inspect_bundle_file
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.exceptions import ValidationError
from lesspaper_ngl.core.logging import get_logger
from lesspaper_ngl.models import (
    BackupRecord,
    BackupRecordStatus,
    BackupSettings,
    BackupVerificationStatus,
    Job,
    JobStatus,
    JobType,
    User,
)
from lesspaper_ngl.services import instance_state as instance_state_service
from lesspaper_ngl.services.jobs import enqueue_job, touch_job_lock

logger = get_logger(__name__)

STAGES = (
    "Preparing",
    "Dumping database",
    "Collecting originals",
    "Copying originals",
    "Writing manifest",
    "Generating checksums",
    "Verifying",
    "Finalising",
    "Completed",
)


async def get_or_create_settings(session: AsyncSession) -> BackupSettings:
    row = await session.get(BackupSettings, 1)
    if row is None:
        row = BackupSettings(id=1)
        session.add(row)
        await session.flush()
    return row


async def has_active_backup_job(session: AsyncSession) -> bool:
    stmt = select(Job.id).where(
        Job.job_type.in_([JobType.BACKUP, JobType.BACKUP_VERIFY]),
        Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]),
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def create_backup_record(session: AsyncSession, *, manual: bool = True) -> BackupRecord:
    settings = await get_or_create_settings(session)
    health = check_repository_health(settings.repository_subdir)
    if not health.available:
        raise RuntimeError(health.message)
    record_id = uuid.uuid4()
    filename = bundle_filename(str(record_id))
    record = BackupRecord(
        id=record_id,
        filename=filename,
        relative_key=relative_key(filename, settings.repository_subdir),
        status=BackupRecordStatus.QUEUED,
        verification_status=BackupVerificationStatus.UNVERIFIED,
    )
    session.add(record)
    await session.flush()
    job = await enqueue_job(
        session,
        job_type=JobType.BACKUP,
        document_id=None,
        priority=50 if manual else 80,
        payload={"backup_record_id": str(record_id), "manual": manual},
        max_retries=0,
    )
    record.job_id = job.id
    await session.flush()
    return record


async def _set_stage(session: AsyncSession, record: BackupRecord, stage: str) -> None:
    record.progress_stage = stage
    await session.flush()


async def _collect_storage_keys(session: AsyncSession) -> tuple[list[str], list[str], int, int]:
    from lesspaper_ngl.models import Document

    docs = (await session.execute(select(Document.storage_key).where(Document.is_trashed.is_(False)))).all()
    storage_keys = sorted({row[0] for row in docs})
    avatars = (
        await session.execute(select(User.avatar_key).where(User.avatar_key.is_not(None)))
    ).all()
    avatar_keys = sorted({row[0] for row in avatars if row[0]})
    count = (
        await session.execute(select(func.count()).select_from(Document).where(Document.is_trashed.is_(False)))
    ).scalar_one()
    original_bytes = 0
    settings = get_settings()
    for key in storage_keys:
        path = settings.originals_path / key
        if path.is_file():
            original_bytes += path.stat().st_size
    for key in avatar_keys:
        path = settings.avatars_path / key
        if path.is_file():
            original_bytes += path.stat().st_size
    return storage_keys, avatar_keys, int(count), original_bytes


async def run_backup_job(session: AsyncSession, job: Job) -> dict[str, Any]:
    record_id = uuid.UUID(job.payload["backup_record_id"])
    record = await session.get(BackupRecord, record_id)
    if record is None:
        raise ValueError("Backup record not found")
    policy = await get_or_create_settings(session)
    repo = repository_path(policy.repository_subdir)
    staging = repo / f".folium-backup-{record.id}.tmp"
    cleanup_staging(staging)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        state = await instance_state_service.get_instance_state(session)
        if state.value in {"restoring", "uninitialised"}:
            raise RuntimeError("Backup unavailable while instance is not ready")
        record.status = BackupRecordStatus.RUNNING
        await _set_stage(session, record, STAGES[0])
        await touch_job_lock(session, job.id)
        await _set_stage(session, record, STAGES[2])
        storage_keys, avatar_keys, doc_count, original_bytes = await _collect_storage_keys(session)
        usage = shutil.disk_usage(repo)
        needed = original_bytes * 2 + 64 * 1024 * 1024
        if usage.free < needed:
            raise RuntimeError("Not enough free space in the backup repository")
        dump_path = staging / "database" / "lesspaper_ngl.dump"
        await _set_stage(session, record, STAGES[1])
        run_pg_dump(dump_path)
        validate_dump_readable(dump_path)
        await touch_job_lock(session, job.id)
        await _set_stage(session, record, STAGES[3])
        settings = get_settings()
        missing: list[str] = []
        for key in storage_keys:
            src = settings.originals_path / key
            dest = staging / "documents" / "originals" / key
            if not src.is_file():
                missing.append(key)
                continue
            copy_file(src, dest)
        for key in avatar_keys:
            src = settings.avatars_path / key
            dest = staging / "documents" / "avatars" / key
            if not src.is_file():
                missing.append(key)
                continue
            copy_file(src, dest)
        if missing:
            raise RuntimeError(f"Missing {len(missing)} file(s) referenced by database")
        await touch_job_lock(session, job.id)
        await _set_stage(session, record, STAGES[4])
        install_id = await instance_state_service.get_installation_id(session)
        manifest = BackupManifest(
            format_version=1,
            folium_version=__version__,
            created_at=datetime.now(UTC).isoformat(),
            database_schema_version=_schema_head(),
            backup_type="full",
            document_count=doc_count,
            original_bytes=original_bytes,
            checksum_algorithm=CHECKSUM_ALGORITHM,
            verification_state=BackupVerificationStatus.UNVERIFIED.value,
            installation_id=install_id,
            source_hostname=socket.gethostname(),
            derived_data_included=False,
            storage_keys=storage_keys,
            avatar_keys=avatar_keys,
        )
        write_manifest(staging, manifest)
        await _set_stage(session, record, STAGES[5])
        members = [p for p in staging.rglob("*") if p.is_file()]
        write_checksums(staging, members)
        if policy.verify_after_backup:
            await _set_stage(session, record, STAGES[6])
            verify_checksums(staging)
        await _set_stage(session, record, STAGES[7])
        bundle = bundle_path(record.filename, policy.repository_subdir)
        size = create_bundle_archive(staging, bundle)
        manifest.backup_bytes = size
        manifest.verification_state = BackupVerificationStatus.HEALTHY.value
        if policy.verify_after_backup:
            result = inspect_bundle_file(bundle, verify_checksums_flag=True)
            if result.verification_status != BackupVerificationStatus.HEALTHY:
                raise RuntimeError("; ".join(result.messages) or "Verification failed")
            record.verification_status = BackupVerificationStatus.HEALTHY
            record.verified_at = datetime.now(UTC)
        else:
            record.verification_status = BackupVerificationStatus.UNVERIFIED
        record.status = BackupRecordStatus.COMPLETED
        record.completed_at = datetime.now(UTC)
        record.size_bytes = size
        record.document_count = doc_count
        record.folium_version = __version__
        record.schema_version = _schema_head()
        record.format_version = 1
        record.manifest = manifest.to_dict()
        record.progress_stage = STAGES[8]
        record.error_message = None
        policy.last_success_at = datetime.now(UTC)
        await apply_retention(session, policy)
        logger.info("Backup completed: %s (%s bytes)", record.filename, size)
        return {"filename": record.filename, "size_bytes": size}
    except Exception as exc:
        logger.exception("Backup failed for %s", record.filename)
        # Commit failure on this session before re-raising. A nested session_scope
        # deadlocks here: the outer transaction still holds the backup_records row.
        record.status = BackupRecordStatus.FAILED
        record.error_message = str(exc)[:2000]
        record.progress_stage = "Failed"
        await session.commit()
        raise
    finally:
        cleanup_staging(staging)


async def run_verify_job(session: AsyncSession, job: Job) -> dict[str, Any]:
    record_id = uuid.UUID(job.payload["backup_record_id"])
    record = await session.get(BackupRecord, record_id)
    if record is None:
        raise ValueError("Backup record not found")
    policy = await get_or_create_settings(session)
    path = bundle_path(record.filename, policy.repository_subdir)
    result = inspect_bundle_file(path, verify_checksums_flag=True)
    record.verification_status = result.verification_status
    record.verified_at = datetime.now(UTC) if result.verification_status == BackupVerificationStatus.HEALTHY else None
    if result.manifest:
        record.manifest = result.manifest.to_dict()
    return {"verification_status": result.verification_status.value, "messages": result.messages}


async def discover_backups(session: AsyncSession) -> list[BackupRecord]:
    policy = await get_or_create_settings(session)
    repo = repository_path(policy.repository_subdir)
    known = {
        r.filename: r
        for r in (await session.execute(select(BackupRecord))).scalars().all()
    }
    if repo.exists():
        for entry in sorted(repo.glob(f"*{BUNDLE_EXTENSION}")):
            try:
                bundle_path(entry.name, policy.repository_subdir)
            except ValidationError:
                continue
            if entry.name not in known:
                record = BackupRecord(
                    filename=entry.name,
                    relative_key=relative_key(entry.name, policy.repository_subdir),
                    status=BackupRecordStatus.COMPLETED,
                    verification_status=BackupVerificationStatus.UNVERIFIED,
                    size_bytes=entry.stat().st_size,
                )
                session.add(record)
                await session.flush()
                known[entry.name] = record
    return sorted(known.values(), key=lambda r: r.created_at or datetime.min.replace(tzinfo=UTC), reverse=True)


def startup_cleanup() -> None:
    settings = get_settings()
    cleanup_temp_glob(settings.backups_path)
    cleanup_temp_glob(settings.backups_path, "*.folium.part")
