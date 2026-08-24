"""Restore coordinator — runs outside the job queue (DB replacement)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from lesspaper_ngl.backup.bundle import cleanup_staging, copy_file, extract_bundle
from lesspaper_ngl.backup.dump import (
    _parse_sync_url,
    run_pg_dump,
    run_pg_restore,
    terminate_other_connections,
    validate_dump_readable,
)
from lesspaper_ngl.backup.paths import bundle_path
from lesspaper_ngl.backup.verify import inspect_bundle_file
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.logging import get_logger
from lesspaper_ngl.db.session import dispose_engine, session_scope
from lesspaper_ngl.models import BackupVerificationStatus, Document, InstanceState, JobType
from lesspaper_ngl.services import instance_state as instance_state_service
from lesspaper_ngl.services.jobs import enqueue_job

logger = get_logger(__name__)

RESTORE_STATE_FILE = ".restore-state.json"

RESTORE_STAGES = (
    "Inspecting",
    "Validating",
    "Safety backup",
    "Restoring database",
    "Restoring files",
    "Running migrations",
    "Scheduling recovery",
    "Completed",
)


@dataclass
class RestoreState:
    active: bool
    stage: str
    filename: str | None
    error: str | None
    started_at: str | None
    completed_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_restore_lock = asyncio.Lock()
_current: RestoreState = RestoreState(
    active=False,
    stage="idle",
    filename=None,
    error=None,
    started_at=None,
    completed_at=None,
)


def _state_path() -> Path:
    return get_settings().backups_path / RESTORE_STATE_FILE


def _write_state_file(state: RestoreState) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")


def get_restore_status() -> RestoreState:
    path = _state_path()
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return RestoreState(**data)
        except (json.JSONDecodeError, TypeError):
            pass
    return _current


async def _run_alembic_upgrade() -> None:
    cwd = Path.cwd()
    for candidate in (Path("/app"), Path(__file__).resolve().parents[3], cwd):
        if (candidate / "alembic.ini").exists():
            cwd = candidate
            break
    result = await asyncio.to_thread(
        subprocess.run,
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        cwd=str(cwd),
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"Database migration after restore failed: {detail[:500]}")


async def _enqueue_recovery() -> None:
    async with session_scope() as session:
        docs = (await session.execute(select(Document.id).where(Document.is_trashed.is_(False)))).all()
        for (doc_id,) in docs:
            await enqueue_job(session, job_type=JobType.THUMBNAIL, document_id=doc_id, priority=200)


async def execute_restore(
    filename: str,
    *,
    subdir: str = "",
    safety_dump: bool = True,
) -> None:
    async with _restore_lock:
        global _current
        settings = get_settings()
        bundle = bundle_path(filename, subdir)
        _current = RestoreState(
            active=True,
            stage=RESTORE_STAGES[0],
            filename=filename,
            error=None,
            started_at=datetime.now(UTC).isoformat(),
            completed_at=None,
        )
        _write_state_file(_current)
        staging = settings.backups_path / f".folium-restore-{uuid.uuid4()}.tmp"
        safety_path: Path | None = None
        entered_restore = False
        try:
            inspect = inspect_bundle_file(bundle, verify_checksums_flag=True)
            if not inspect.compatible:
                raise RuntimeError("; ".join(inspect.messages) or "Backup incompatible")
            if inspect.verification_status not in {
                BackupVerificationStatus.HEALTHY,
                BackupVerificationStatus.UNVERIFIED,
            }:
                raise RuntimeError(f"Backup verification status: {inspect.verification_status.value}")
            _current.stage = RESTORE_STAGES[1]
            _write_state_file(_current)
            async with session_scope() as session:
                await instance_state_service.set_instance_state(session, InstanceState.RESTORING)
            entered_restore = True
            cleanup_staging(staging)
            extract_bundle(bundle, staging)
            dump_path = staging / "database" / "lesspaper_ngl.dump"
            validate_dump_readable(dump_path)
            if safety_dump:
                _current.stage = RESTORE_STAGES[2]
                _write_state_file(_current)
                safety_path = settings.backups_path / f".pre-restore-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.dump"
                run_pg_dump(safety_path)
            _current.stage = RESTORE_STAGES[3]
            _write_state_file(_current)
            terminate_other_connections()
            params = _parse_sync_url(settings.database_url_sync)
            run_pg_restore(params, dump_path, clean=True)
            await dispose_engine()
            _current.stage = RESTORE_STAGES[4]
            _write_state_file(_current)
            originals_root = staging / "documents" / "originals"
            if originals_root.exists():
                for src in originals_root.rglob("*"):
                    if src.is_file():
                        rel = src.relative_to(originals_root)
                        dest = settings.originals_path / rel
                        copy_file(src, dest)
            avatars_root = staging / "documents" / "avatars"
            if avatars_root.exists():
                for src in avatars_root.rglob("*"):
                    if src.is_file():
                        rel = src.relative_to(avatars_root)
                        dest = settings.avatars_path / rel
                        copy_file(src, dest)
            _current.stage = RESTORE_STAGES[5]
            _write_state_file(_current)
            await _run_alembic_upgrade()
            async with session_scope() as session:
                await instance_state_service.set_instance_state(session, InstanceState.RECOVERING)
            _current.stage = RESTORE_STAGES[6]
            _write_state_file(_current)
            await _enqueue_recovery()
            async with session_scope() as session:
                await instance_state_service.ensure_installation_id(session)
                await instance_state_service.set_instance_state(session, InstanceState.READY)
            _current = RestoreState(
                active=False,
                stage=RESTORE_STAGES[7],
                filename=filename,
                error=None,
                started_at=_current.started_at,
                completed_at=datetime.now(UTC).isoformat(),
            )
            _write_state_file(_current)
            logger.info("Restore completed from %s", filename)
        except Exception as exc:
            logger.exception("Restore failed at stage %s", _current.stage)
            _current = RestoreState(
                active=False,
                stage="Failed",
                filename=filename,
                error=str(exc)[:2000],
                started_at=_current.started_at,
                completed_at=datetime.now(UTC).isoformat(),
            )
            _write_state_file(_current)
            if entered_restore:
                try:
                    async with session_scope() as session:
                        await instance_state_service.set_instance_state(session, InstanceState.FAILED)
                except Exception:  # noqa: BLE001
                    pass
            if safety_path and safety_path.is_file():
                try:
                    params = _parse_sync_url(get_settings().database_url_sync)
                    terminate_other_connections()
                    run_pg_restore(params, safety_path, clean=True)
                    await dispose_engine()
                    await _run_alembic_upgrade()
                except Exception:  # noqa: BLE001
                    logger.exception("Safety rollback failed")
            raise
        finally:
            cleanup_staging(staging)


async def start_restore_background(
    filename: str,
    *,
    subdir: str = "",
    safety_dump: bool = True,
    background_tasks: Any | None = None,
) -> None:
    if background_tasks is not None:
        background_tasks.add_task(execute_restore, filename, subdir=subdir, safety_dump=safety_dump)
        return
    asyncio.create_task(execute_restore(filename, subdir=subdir, safety_dump=safety_dump))
