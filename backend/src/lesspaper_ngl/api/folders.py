"""Folder CRUD and tree endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.api.schemas import (
    FolderCreate,
    FolderDeleteRequest,
    FolderOut,
    FolderUpdate,
    MessageOut,
)
from lesspaper_ngl.auth.deps import CurrentUser, SafeSession
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.services import folders as folder_service
from lesspaper_ngl.storage.service import StorageService

router = APIRouter(prefix="/api/folders", tags=["folders"])


async def _folder_out(session: AsyncSession, folder, owner_id: uuid.UUID) -> FolderOut:
    from datetime import timedelta

    from lesspaper_ngl.core.config import get_settings

    counts = await folder_service.folder_counts(session, owner_id)
    children_count, document_count = counts.get(folder.id, (0, 0))
    purge_after = None
    if folder.is_trashed and folder.trashed_at is not None:
        purge_after = folder.trashed_at + timedelta(days=get_settings().trash_retention_days)
    return FolderOut(
        id=folder.id,
        name=folder.name,
        parent_id=folder.parent_id,
        kind=folder.kind.value,
        sort_order=folder.sort_order,
        path_cache=folder.path_cache,
        is_trashed=folder.is_trashed,
        trashed_at=folder.trashed_at,
        created_at=folder.created_at,
        updated_at=folder.updated_at,
        children_count=children_count,
        document_count=document_count,
        purge_after=purge_after,
    )


@router.get("", response_model=list[FolderOut])
async def list_folders(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    trashed: bool = False,
) -> list[FolderOut]:
    if trashed:
        folders = await folder_service.list_trashed_folders(db, _user.id)
    else:
        folders = await folder_service.list_folder_tree(db, _user.id)
    return [await _folder_out(db, f, _user.id) for f in folders]


@router.post("", response_model=FolderOut, status_code=201)
async def create_folder(
    body: FolderCreate,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FolderOut:
    folder = await folder_service.create_folder(
        db,
        name=body.name,
        parent_id=body.parent_id,
        owner_id=_user.id,
    )
    return await _folder_out(db, folder, _user.id)


@router.get("/{folder_id}", response_model=FolderOut)
async def get_folder(
    folder_id: uuid.UUID,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FolderOut:
    folder = await folder_service.get_folder(db, folder_id, owner_id=_user.id)
    return await _folder_out(db, folder, _user.id)


@router.patch("/{folder_id}", response_model=FolderOut)
async def update_folder(
    folder_id: uuid.UUID,
    body: FolderUpdate,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FolderOut:
    folder = await folder_service.get_folder(db, folder_id, owner_id=_user.id)
    if body.name is not None:
        folder = await folder_service.rename_folder(db, folder_id, body.name, owner_id=_user.id)
    if body.parent_id is not None:
        folder = await folder_service.move_folder(db, folder_id, body.parent_id, owner_id=_user.id)
    if body.sort_order is not None:
        folder = await folder_service.get_folder(db, folder_id, owner_id=_user.id)
        folder.sort_order = body.sort_order
        await db.flush()
        await db.refresh(folder)
    return await _folder_out(db, folder, _user.id)


@router.post("/{folder_id}/trash", response_model=FolderOut)
async def trash_folder(
    folder_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FolderOut:
    folder = await folder_service.trash_folder(db, folder_id, owner_id=_user.id)
    return await _folder_out(db, folder, _user.id)


@router.post("/{folder_id}/restore", response_model=FolderOut)
async def restore_folder(
    folder_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FolderOut:
    folder = await folder_service.restore_folder(db, folder_id, owner_id=_user.id)
    return await _folder_out(db, folder, _user.id)


@router.post("/{folder_id}/purge", response_model=MessageOut)
async def purge_folder(
    folder_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    """Permanently delete a trashed folder and everything inside it."""
    result = await folder_service.permanently_delete_trashed_subtree(
        db,
        folder_id,
        owner_id=_user.id,
        storage=StorageService(),
    )
    return MessageOut(
        message=(
            f"Permanently deleted {result['deleted_documents']} document(s) "
            f"and {result['deleted_folders']} folder(s)"
        )
    )


@router.delete("/{folder_id}", status_code=204)
async def delete_folder(
    folder_id: uuid.UUID,
    body: FolderDeleteRequest,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await folder_service.delete_folder(
        db,
        folder_id,
        owner_id=_user.id,
        strategy=body.strategy,
        confirm_destructive=body.confirm_destructive,
    )
