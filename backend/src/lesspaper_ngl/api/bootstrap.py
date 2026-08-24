"""First-run bootstrap and restore API (unauthenticated when uninitialised)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.api.schemas import (
    BackupInspectOut,
    BackupRecordOut,
    BootstrapInspectIn,
    BootstrapRestoreIn,
    BootstrapStatusOut,
)
from lesspaper_ngl.auth import service as auth_service
from lesspaper_ngl.backup.manifest import BUNDLE_EXTENSION
from lesspaper_ngl.backup.paths import bundle_path, repository_path
from lesspaper_ngl.backup.restore import get_restore_status, start_restore_background
from lesspaper_ngl.backup.verify import inspect_bundle_file
from lesspaper_ngl.bootstrap import ensure_ai_settings
from lesspaper_ngl.core.exceptions import ValidationError
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.models import BackupRecordStatus, InstanceState
from lesspaper_ngl.services import backup as backup_service
from lesspaper_ngl.services import folders as folder_service
from lesspaper_ngl.services import instance_state as instance_state_service
from lesspaper_ngl.services.users import check_forgot_rate_limit

router = APIRouter(prefix="/api/bootstrap", tags=["bootstrap"])


async def _require_uninitialised(db: AsyncSession) -> None:
    state = await instance_state_service.get_instance_state(db)
    if state != InstanceState.UNINITIALISED:
        raise HTTPException(status_code=403, detail="Bootstrap endpoints are not available")


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@router.get("/status", response_model=BootstrapStatusOut)
async def bootstrap_status(db: Annotated[AsyncSession, Depends(get_db)]) -> BootstrapStatusOut:
    state = await instance_state_service.get_instance_state(db)
    return BootstrapStatusOut(
        instance_state=state.value,
        ready=state == InstanceState.READY,
    )


@router.post("/setup", response_model=BootstrapStatusOut)
async def bootstrap_setup(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BootstrapStatusOut:
    await _require_uninitialised(db)
    check_forgot_rate_limit(f"bootstrap-setup:{_client_ip(request)}")
    await instance_state_service.set_instance_state(db, InstanceState.INITIALISING)
    admin = await auth_service.ensure_admin_user(db)
    await folder_service.ensure_system_folders(db, admin.id)
    await ensure_ai_settings(db)
    await instance_state_service.ensure_installation_id(db)
    await instance_state_service.set_instance_state(db, InstanceState.READY)
    return BootstrapStatusOut(instance_state=InstanceState.READY.value, ready=True)


@router.get("/backups", response_model=list[BackupRecordOut])
async def bootstrap_list_backups(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[BackupRecordOut]:
    await _require_uninitialised(db)
    policy = await backup_service.get_or_create_settings(db)
    repo = repository_path(policy.repository_subdir)
    items: list[BackupRecordOut] = []
    if not repo.exists():
        return items
    for entry in sorted(repo.glob(f"*{BUNDLE_EXTENSION}"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            result = inspect_bundle_file(entry, verify_checksums_flag=False)
            manifest = result.manifest
            items.append(
                BackupRecordOut(
                    filename=entry.name,
                    relative_key=entry.name,
                    size_bytes=entry.stat().st_size,
                    document_count=manifest.document_count,
                    folium_version=manifest.folium_version,
                    schema_version=manifest.database_schema_version,
                    format_version=manifest.format_version,
                    status=BackupRecordStatus.COMPLETED.value,
                    verification_status=result.verification_status.value,
                    created_at=datetime.fromtimestamp(entry.stat().st_mtime, tz=UTC),
                )
            )
        except Exception:  # noqa: BLE001
            continue
    return items


@router.post("/backups/inspect", response_model=BackupInspectOut)
async def bootstrap_inspect(
    body: BootstrapInspectIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BackupInspectOut:
    await _require_uninitialised(db)
    check_forgot_rate_limit(f"bootstrap-inspect:{_client_ip(request)}")
    policy = await backup_service.get_or_create_settings(db)
    path = bundle_path(body.filename, policy.repository_subdir)
    result = inspect_bundle_file(path, verify_checksums_flag=True)
    return BackupInspectOut(
        manifest=result.manifest.to_dict(),
        verification_status=result.verification_status.value,
        compatible=result.compatible,
        messages=result.messages,
    )


@router.post("/restore", status_code=status.HTTP_202_ACCEPTED)
async def bootstrap_restore(
    body: BootstrapRestoreIn,
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    await _require_uninitialised(db)
    if not body.confirm:
        raise ValidationError("Restore requires confirm=true")
    check_forgot_rate_limit(f"bootstrap-restore:{_client_ip(request)}")
    status_obj = get_restore_status()
    if status_obj.active:
        raise HTTPException(status_code=409, detail="A restore is already in progress")
    policy = await backup_service.get_or_create_settings(db)
    path = bundle_path(body.filename, policy.repository_subdir)
    result = inspect_bundle_file(path, verify_checksums_flag=True)
    if not result.compatible:
        raise HTTPException(status_code=400, detail="; ".join(result.messages))
    await start_restore_background(
        body.filename,
        subdir=policy.repository_subdir,
        safety_dump=False,
        background_tasks=background_tasks,
    )
    return {"status": "accepted", "stage": get_restore_status().stage}
