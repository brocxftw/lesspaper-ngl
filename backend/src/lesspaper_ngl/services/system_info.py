"""Allowlisted system and storage facts available inside the application."""

from __future__ import annotations

import os
import platform
import shutil
import socket
import time
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import func, inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl import __version__
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.models import AppSetting, Document, Job, JobStatus
from lesspaper_ngl.storage.service import StorageService
from lesspaper_ngl.workers.healthcheck import WORKER_HEARTBEAT_KEY

PROCESS_STARTED_MONOTONIC = time.monotonic()


def _cgroup_value(name: str) -> str | None:
    try:
        value = (Path("/sys/fs/cgroup") / name).read_text(encoding="utf-8").strip()
        return None if value == "max" else value
    except OSError:
        return None


def _directory_size(path: Path) -> int | None:
    try:
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
    except OSError:
        return None


async def system_summary(db: AsyncSession) -> dict[str, Any]:
    storage = StorageService().check_health()
    counts = (
        await db.execute(
            select(
                func.count(Document.id),
                func.count(Document.id).filter(Document.document_indexed.is_(True)),
            )
        )
    ).one()
    job_rows = (
        await db.execute(
            select(Job.status, func.count(Job.id))
            .where(Job.status.in_([JobStatus.QUEUED, JobStatus.RUNNING]))
            .group_by(Job.status)
        )
    ).all()
    jobs: dict[JobStatus, int] = {status: int(count) for status, count in job_rows}
    heartbeat = await db.get(AppSetting, WORKER_HEARTBEAT_KEY)
    last_seen = None
    if heartbeat and isinstance(heartbeat.value, dict):
        with suppress(TypeError, ValueError):
            last_seen = datetime.fromisoformat(str(heartbeat.value.get("at")))
    worker_ok = bool(last_seen and last_seen >= datetime.now(UTC) - timedelta(seconds=30))
    connection = await db.connection()
    has_alembic_table = await connection.run_sync(
        lambda conn: inspect(conn).has_table("alembic_version")
    )
    revision = "metadata-created"
    if has_alembic_table:
        revision = (
            await db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
        ).scalar_one_or_none() or "unknown"
    return {
        "version": __version__,
        "schema_revision": revision,
        "process_uptime_seconds": int(time.monotonic() - PROCESS_STARTED_MONOTONIC),
        "deployment_mode": "Containerized application",
        "services": {
            "web": "configured",
            "api": "healthy",
            "worker": "healthy" if worker_ok else "degraded",
            "db": "healthy",
        },
        "database_status": "healthy",
        "storage_status": storage.status,
        "worker_status": "healthy" if worker_ok else "unavailable",
        "worker_last_seen_at": last_seen,
        "document_count": int(counts[0]),
        "indexed_document_count": int(counts[1]),
        "queued_jobs": int(jobs.get(JobStatus.QUEUED, 0)),
        "running_jobs": int(jobs.get(JobStatus.RUNNING, 0)),
        "runtime": {
            "scope": "Container-visible runtime resources",
            "os": platform.system(),
            "architecture": platform.machine(),
            "hostname": socket.gethostname(),
            "cpu_count_visible": os.cpu_count(),
            "cgroup_memory_limit_bytes": _cgroup_value("memory.max"),
            "cgroup_cpu_limit": _cgroup_value("cpu.max"),
            "physical_host_hardware": "Unavailable in current deployment",
            "docker_engine": "Unavailable without host integration",
        },
    }


async def storage_metrics(db: AsyncSession) -> dict[str, Any]:
    settings = get_settings()
    root = settings.documents_path
    try:
        usage = shutil.disk_usage(root)
        total: int | None = usage.total
        used: int | None = usage.used
        free: int | None = usage.free
    except OSError:
        total = used = free = None
    categories = {
        "originals": _directory_size(settings.originals_path),
        "previews": _directory_size(settings.previews_path),
        "thumbnails": _directory_size(settings.thumbnails_path),
        "avatars": _directory_size(settings.avatars_path),
        "ocr_cache": None,
    }
    known = [value for value in categories.values() if value is not None]
    try:
        db_bytes = int(
            (await db.execute(text("SELECT pg_database_size(current_database())"))).scalar_one()
        )
        relation_rows = (
            await db.execute(
                text(
                    """
                    SELECT name, pg_total_relation_size(name::regclass)
                    FROM (VALUES
                      ('document_chunks'), ('documents'),
                      ('ai_usage'), ('application_logs')
                    ) AS relations(name)
                    """
                )
            )
        ).all()
        database_categories = {str(name): int(size) for name, size in relation_rows}
    except Exception:
        db_bytes = None
        database_categories = {}
    return {
        "configured_source": settings.documents_host_source,
        "container_path": str(root),
        "disk_total_bytes": total,
        "disk_used_bytes": used,
        "disk_free_bytes": free,
        "folium_bytes": sum(known) if known else None,
        "categories": categories,
        "database_bytes": db_bytes,
        "database_categories": database_categories,
        "message": (
            "Filesystem capacity covers the document-library mount only. "
            "Database size is reported separately."
        ),
    }
