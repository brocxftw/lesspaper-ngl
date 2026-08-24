"""Health check endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl import __version__
from lesspaper_ngl.api.schemas import HealthOut, StorageHealthOut, WorkerHealthOut
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.models import AppSetting
from lesspaper_ngl.services import instance_state as instance_state_service
from lesspaper_ngl.storage.service import StorageService
from lesspaper_ngl.workers.healthcheck import (
    WORKER_HEARTBEAT_KEY,
    heartbeat_is_fresh,
    parse_heartbeat_at,
)

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
async def health(db: AsyncSession = Depends(get_db)) -> HealthOut:
    state = await instance_state_service.get_instance_state(db)
    return HealthOut(status="ok", version=__version__, instance_state=state.value)


@router.get("/health/database", response_model=HealthOut)
async def health_database(db: AsyncSession = Depends(get_db)) -> HealthOut:
    await db.execute(text("SELECT 1"))
    return HealthOut(status="ok", version=__version__)


@router.get("/health/worker", response_model=WorkerHealthOut)
async def health_worker(db: AsyncSession = Depends(get_db)) -> WorkerHealthOut:
    heartbeat = await db.get(AppSetting, WORKER_HEARTBEAT_KEY)
    value = heartbeat.value if heartbeat is not None else None
    last_seen = parse_heartbeat_at(value)
    worker_id = None
    if isinstance(value, dict):
        raw_id = value.get("worker_id")
        worker_id = str(raw_id) if raw_id else None
    status = "healthy" if heartbeat_is_fresh(last_seen) else "unavailable"
    return WorkerHealthOut(
        status=status,
        version=__version__,
        last_seen_at=last_seen,
        worker_id=worker_id,
    )


@router.get("/health/storage", response_model=StorageHealthOut)
async def health_storage() -> StorageHealthOut:
    health = await asyncio.to_thread(StorageService().check_health)
    return StorageHealthOut(
        status=health.status,
        documents_ok=health.documents_ok,
        consume_ok=health.consume_ok,
        export_ok=health.export_ok,
        documents_path=health.documents_path,
        consume_path=health.consume_path,
        export_path=health.export_path,
        message=health.message,
    )
