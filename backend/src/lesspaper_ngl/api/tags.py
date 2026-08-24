"""Tag, document type, and correspondent endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.api.schemas import (
    MessageOut,
    NamedEntityCreate,
    NamedEntityOut,
    TagCreate,
    TagMerge,
    TagOut,
    TagUpdate,
)
from lesspaper_ngl.auth.deps import CurrentUser, SafeSession
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.services import tags as tag_service

router = APIRouter(tags=["tags"])


# ---- Tags ----


@router.get("/api/tags", response_model=list[TagOut])
async def list_tags(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[TagOut]:
    rows = await tag_service.list_tags(db, _user.id)
    return [
        TagOut(
            id=tag.id,
            name=tag.name,
            color=tag.color,
            slug=tag.slug,
            document_count=count,
        )
        for tag, count in rows
    ]


@router.post("/api/tags", response_model=TagOut, status_code=201)
async def create_tag(
    body: TagCreate,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TagOut:
    tag = await tag_service.create_tag(
        db,
        body.name,
        _user.id,
        body.color,
    )
    return TagOut(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        slug=tag.slug,
        document_count=0,
    )


@router.patch("/api/tags/{tag_id}", response_model=TagOut)
async def update_tag(
    tag_id: uuid.UUID,
    body: TagUpdate,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TagOut:
    tag = await tag_service.update_tag(
        db,
        tag_id,
        owner_id=_user.id,
        name=body.name,
        color=body.color,
    )
    rows = await tag_service.list_tags(db, _user.id)
    count = next((c for t, c in rows if t.id == tag.id), 0)
    return TagOut(
        id=tag.id,
        name=tag.name,
        color=tag.color,
        slug=tag.slug,
        document_count=count,
    )


@router.delete("/api/tags/{tag_id}", response_model=MessageOut)
async def delete_tag(
    tag_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    await tag_service.delete_tag(db, tag_id, owner_id=_user.id)
    return MessageOut(message="Tag deleted")


@router.post("/api/tags/merge", response_model=TagOut)
async def merge_tags(
    body: TagMerge,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TagOut:
    target, count = await tag_service.merge_tags(
        db,
        source_tag_id=body.source_tag_id,
        target_tag_id=body.target_tag_id,
        owner_id=_user.id,
    )
    return TagOut(
        id=target.id,
        name=target.name,
        color=target.color,
        slug=target.slug,
        document_count=count,
    )


# ---- Document types ----


@router.get("/api/document-types", response_model=list[NamedEntityOut])
async def list_document_types(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[NamedEntityOut]:
    items = await tag_service.list_document_types(db, _user.id)
    return [NamedEntityOut(id=t.id, name=t.name, slug=t.slug) for t in items]


@router.post("/api/document-types", response_model=NamedEntityOut, status_code=201)
async def create_document_type(
    body: NamedEntityCreate,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NamedEntityOut:
    obj = await tag_service.create_document_type(db, body.name, _user.id)
    return NamedEntityOut(id=obj.id, name=obj.name, slug=obj.slug)


@router.delete("/api/document-types/{type_id}", response_model=MessageOut)
async def delete_document_type(
    type_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    await tag_service.delete_document_type(db, type_id, owner_id=_user.id)
    return MessageOut(message="Document type deleted")


# ---- Correspondents ----


@router.get("/api/correspondents", response_model=list[NamedEntityOut])
async def list_correspondents(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[NamedEntityOut]:
    items = await tag_service.list_correspondents(db, _user.id)
    return [NamedEntityOut(id=c.id, name=c.name, slug=c.slug) for c in items]


@router.post("/api/correspondents", response_model=NamedEntityOut, status_code=201)
async def create_correspondent(
    body: NamedEntityCreate,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NamedEntityOut:
    obj = await tag_service.create_correspondent(db, body.name, _user.id)
    return NamedEntityOut(id=obj.id, name=obj.name, slug=obj.slug)


@router.delete("/api/correspondents/{corr_id}", response_model=MessageOut)
async def delete_correspondent(
    corr_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    await tag_service.delete_correspondent(db, corr_id, owner_id=_user.id)
    return MessageOut(message="Correspondent deleted")
