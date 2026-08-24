"""Trash workspace endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.api.schemas import MessageOut, TrashPurgeOut
from lesspaper_ngl.auth.deps import CurrentUser, SafeSession
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.models import Document, Folder, FolderKind
from lesspaper_ngl.services import documents as doc_service
from lesspaper_ngl.storage.service import StorageService

router = APIRouter(prefix="/api/trash", tags=["trash"])


@router.get("/count")
async def trash_count(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, int]:
    docs = (
        await db.execute(
            select(func.count())
            .select_from(Document)
            .where(
                Document.owner_id == _user.id,
                Document.is_trashed.is_(True),
            )
        )
    ).scalar_one()
    folders = (
        await db.execute(
            select(func.count())
            .select_from(Folder)
            .where(
                Folder.owner_id == _user.id,
                Folder.is_trashed.is_(True),
                Folder.kind == FolderKind.NORMAL,
            )
        )
    ).scalar_one()
    return {
        "documents": int(docs),
        "folders": int(folders),
        "total": int(docs) + int(folders),
        "retention_days": get_settings().trash_retention_days,
    }


@router.post("/purge", response_model=TrashPurgeOut)
async def purge_trash(
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TrashPurgeOut:
    """Permanently delete trash items past the retention window."""
    result = await doc_service.purge_expired_trash(
        db,
        owner_id=_user.id,
        storage=StorageService(),
    )
    return TrashPurgeOut(**result)


@router.post("/empty", response_model=MessageOut)
async def empty_trash(
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    """Permanently delete all trashed documents and empty trashed folders now."""
    result = await doc_service.empty_trash(
        db,
        owner_id=_user.id,
        storage=StorageService(),
    )
    return MessageOut(
        message=(
            f"Permanently deleted {result['deleted_documents']} document(s) "
            f"and {result['deleted_folders']} folder(s)"
        )
    )
