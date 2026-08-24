"""Tag, document type, and correspondent services."""

from __future__ import annotations

import uuid

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.core.exceptions import ConflictError, NotFoundError, ValidationError
from lesspaper_ngl.core.utils import slugify
from lesspaper_ngl.models import Correspondent, Document, DocumentTag, DocumentType, Tag


async def create_tag(
    session: AsyncSession,
    name: str,
    owner_id: uuid.UUID,
    color: str = "#64748b",
) -> Tag:
    name = name.strip()
    if not name:
        raise ValidationError("Tag name is required")
    slug = slugify(name)
    existing = (
        await session.execute(
            select(Tag).where(
                Tag.owner_id == owner_id,
                (Tag.slug == slug) | (Tag.name == name),
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("Tag already exists")
    tag = Tag(owner_id=owner_id, name=name, slug=slug, color=color)
    session.add(tag)
    await session.flush()
    return tag


async def list_tags(session: AsyncSession, owner_id: uuid.UUID) -> list[tuple[Tag, int]]:
    rows = await session.execute(
        select(Tag, func.count(Document.id))
        .outerjoin(DocumentTag, DocumentTag.tag_id == Tag.id)
        .outerjoin(
            Document,
            and_(
                Document.id == DocumentTag.document_id,
                Document.owner_id == owner_id,
            ),
        )
        .where(Tag.owner_id == owner_id)
        .group_by(Tag.id)
        .order_by(Tag.name)
    )
    return [(row[0], int(row[1])) for row in rows.all()]


async def update_tag(
    session: AsyncSession,
    tag_id: uuid.UUID,
    *,
    owner_id: uuid.UUID,
    name: str | None = None,
    color: str | None = None,
) -> Tag:
    tag = await session.get(Tag, tag_id)
    if tag is None or tag.owner_id != owner_id:
        raise NotFoundError("Tag not found")
    if name is not None:
        name = name.strip()
        slug = slugify(name)
        conflict = (
            await session.execute(
                select(Tag).where(
                    Tag.owner_id == owner_id,
                    Tag.slug == slug,
                    Tag.id != tag_id,
                )
            )
        ).scalar_one_or_none()
        if conflict:
            raise ConflictError("Tag already exists")
        tag.name = name
        tag.slug = slug
    if color is not None:
        tag.color = color
    await session.flush()
    return tag


async def delete_tag(session: AsyncSession, tag_id: uuid.UUID, *, owner_id: uuid.UUID) -> None:
    tag = await session.get(Tag, tag_id)
    if tag is None or tag.owner_id != owner_id:
        raise NotFoundError("Tag not found")
    await session.delete(tag)


async def merge_tags(
    session: AsyncSession,
    *,
    source_tag_id: uuid.UUID,
    target_tag_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> tuple[Tag, int]:
    if source_tag_id == target_tag_id:
        raise ValidationError("Cannot merge a tag into itself")
    source = await session.get(Tag, source_tag_id)
    target = await session.get(Tag, target_tag_id)
    if source is None or source.owner_id != owner_id:
        raise NotFoundError("Source tag not found")
    if target is None or target.owner_id != owner_id:
        raise NotFoundError("Target tag not found")

    links = (
        await session.execute(select(DocumentTag).where(DocumentTag.tag_id == source_tag_id))
    ).scalars()
    for link in links:
        conflict = (
            await session.execute(
                select(DocumentTag).where(
                    DocumentTag.document_id == link.document_id,
                    DocumentTag.tag_id == target_tag_id,
                )
            )
        ).scalar_one_or_none()
        if conflict is not None:
            await session.delete(link)
        else:
            link.tag_id = target_tag_id

    await session.delete(source)
    await session.flush()

    count = (
        await session.execute(
            select(func.count(Document.id))
            .select_from(DocumentTag)
            .join(Document, Document.id == DocumentTag.document_id)
            .where(
                DocumentTag.tag_id == target_tag_id,
                Document.owner_id == owner_id,
                Document.is_trashed.is_(False),
            )
        )
    ).scalar_one()
    return target, int(count)


async def create_document_type(
    session: AsyncSession, name: str, owner_id: uuid.UUID
) -> DocumentType:
    name = name.strip()
    slug = slugify(name)
    existing = (
        await session.execute(
            select(DocumentType).where(
                DocumentType.owner_id == owner_id,
                DocumentType.slug == slug,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("Document type already exists")
    obj = DocumentType(owner_id=owner_id, name=name, slug=slug)
    session.add(obj)
    await session.flush()
    return obj


async def list_document_types(session: AsyncSession, owner_id: uuid.UUID) -> list[DocumentType]:
    return list(
        (
            await session.execute(
                select(DocumentType)
                .where(DocumentType.owner_id == owner_id)
                .order_by(DocumentType.name)
            )
        )
        .scalars()
        .all()
    )


async def delete_document_type(
    session: AsyncSession, type_id: uuid.UUID, *, owner_id: uuid.UUID
) -> None:
    obj = await session.get(DocumentType, type_id)
    if obj is None or obj.owner_id != owner_id:
        raise NotFoundError("Document type not found")
    await session.delete(obj)


async def create_correspondent(
    session: AsyncSession, name: str, owner_id: uuid.UUID
) -> Correspondent:
    name = name.strip()
    slug = slugify(name)
    existing = (
        await session.execute(
            select(Correspondent).where(
                Correspondent.owner_id == owner_id,
                Correspondent.slug == slug,
            )
        )
    ).scalar_one_or_none()
    if existing:
        raise ConflictError("Correspondent already exists")
    obj = Correspondent(owner_id=owner_id, name=name, slug=slug)
    session.add(obj)
    await session.flush()
    return obj


async def list_correspondents(session: AsyncSession, owner_id: uuid.UUID) -> list[Correspondent]:
    return list(
        (
            await session.execute(
                select(Correspondent)
                .where(Correspondent.owner_id == owner_id)
                .order_by(Correspondent.name)
            )
        )
        .scalars()
        .all()
    )


async def delete_correspondent(
    session: AsyncSession, corr_id: uuid.UUID, *, owner_id: uuid.UUID
) -> None:
    obj = await session.get(Correspondent, corr_id)
    if obj is None or obj.owner_id != owner_id:
        raise NotFoundError("Correspondent not found")
    await session.delete(obj)
