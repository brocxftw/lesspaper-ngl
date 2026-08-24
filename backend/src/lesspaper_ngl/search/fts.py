"""PostgreSQL full-text search helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.models import Document, DocumentPage, Tag
from lesspaper_ngl.search.filters import DocumentSearchFilters, apply_document_search_filters

_ENGLISH_CONFIG = "english"


@dataclass(frozen=True)
class DocumentSearchHit:
    document_id: uuid.UUID
    title: str
    rank: float
    snippet: str | None = None


@dataclass(frozen=True)
class PageSearchHit:
    page_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int
    rank: float
    snippet: str
    text: str


async def refresh_document_search_vector(session: AsyncSession, document_id: uuid.UUID) -> None:
    """Rebuild the document-level tsvector from title, notes, and extracted text."""
    doc = await session.get(Document, document_id)
    if doc is None:
        return

    tag_names = await _document_tag_names(session, document_id)
    payload = _join_search_parts(
        doc.title,
        doc.notes,
        doc.extracted_text,
        " ".join(tag_names) if tag_names else None,
        doc.original_filename,
    )
    await session.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(search_vector=func.to_tsvector(_ENGLISH_CONFIG, payload))
    )


async def refresh_page_search_vectors(session: AsyncSession, document_id: uuid.UUID) -> None:
    """Rebuild page-level tsvectors for a document."""
    result = await session.execute(
        select(DocumentPage.id, DocumentPage.text).where(DocumentPage.document_id == document_id)
    )
    for page_id, page_text in result.all():
        await session.execute(
            update(DocumentPage)
            .where(DocumentPage.id == page_id)
            .values(search_vector=func.to_tsvector(_ENGLISH_CONFIG, page_text or ""))
        )


async def build_document_search_vector(session: AsyncSession, document_id: uuid.UUID) -> None:
    """Alias for refreshing a document search vector."""
    await refresh_document_search_vector(session, document_id)


def _base_filters(
    *,
    owner_id: uuid.UUID,
    folder_id: uuid.UUID | None = None,
    folder_ids: list[uuid.UUID] | None = None,
    include_trashed: bool = False,
    inbox_only: bool | None = None,
    filters: DocumentSearchFilters | None = None,
) -> DocumentSearchFilters:
    if filters is not None:
        return filters
    return DocumentSearchFilters(
        owner_id=owner_id,
        folder_id=folder_id,
        folder_ids=folder_ids,
        include_trashed=include_trashed,
        inbox=inbox_only,
    )


async def search_documents(
    session: AsyncSession,
    query: str,
    *,
    owner_id: uuid.UUID,
    folder_id: uuid.UUID | None = None,
    folder_ids: list[uuid.UUID] | None = None,
    include_trashed: bool = False,
    inbox_only: bool | None = None,
    filters: DocumentSearchFilters | None = None,
    limit: int = 20,
    offset: int = 0,
) -> list[DocumentSearchHit]:
    """Search documents using websearch_to_tsquery ranking."""
    cleaned = query.strip()
    if not cleaned:
        return []

    tsquery = func.websearch_to_tsquery(_ENGLISH_CONFIG, cleaned)
    rank = func.ts_rank_cd(Document.search_vector, tsquery).label("rank")
    headline = func.ts_headline(
        _ENGLISH_CONFIG,
        func.coalesce(Document.extracted_text, Document.title),
        tsquery,
        "MaxFragments=2, MinWords=5, MaxWords=20",
    ).label("snippet")

    stmt = (
        select(Document.id, Document.title, rank, headline)
        .where(Document.search_vector.op("@@")(tsquery))
        .order_by(rank.desc(), Document.modified_date.desc())
        .limit(max(1, min(limit, 100)))
        .offset(max(0, offset))
    )
    stmt = apply_document_search_filters(
        stmt,
        _base_filters(
            owner_id=owner_id,
            folder_id=folder_id,
            folder_ids=folder_ids,
            include_trashed=include_trashed,
            inbox_only=inbox_only,
            filters=filters,
        ),
    )

    rows = await session.execute(stmt)
    return [
        DocumentSearchHit(
            document_id=row.id,
            title=row.title,
            rank=float(row.rank or 0.0),
            snippet=row.snippet,
        )
        for row in rows.all()
    ]


async def count_documents_matching(
    session: AsyncSession,
    query: str,
    *,
    filters: DocumentSearchFilters,
) -> int:
    cleaned = query.strip()
    if not cleaned:
        return 0
    tsquery = func.websearch_to_tsquery(_ENGLISH_CONFIG, cleaned)
    stmt = select(func.count(Document.id)).where(Document.search_vector.op("@@")(tsquery))
    stmt = apply_document_search_filters(stmt, filters)
    return int((await session.execute(stmt)).scalar_one())


async def search_pages(
    session: AsyncSession,
    query: str,
    *,
    owner_id: uuid.UUID,
    folder_id: uuid.UUID | None = None,
    folder_ids: list[uuid.UUID] | None = None,
    include_trashed: bool = False,
    filters: DocumentSearchFilters | None = None,
    limit: int = 40,
    offset: int = 0,
) -> list[PageSearchHit]:
    """Search document pages for keyword retrieval."""
    cleaned = query.strip()
    if not cleaned:
        return []

    tsquery = func.websearch_to_tsquery(_ENGLISH_CONFIG, cleaned)
    rank = func.ts_rank_cd(DocumentPage.search_vector, tsquery).label("rank")
    headline = func.ts_headline(
        _ENGLISH_CONFIG,
        DocumentPage.text,
        tsquery,
        "MaxFragments=2, MinWords=5, MaxWords=20",
    ).label("snippet")

    stmt = (
        select(
            DocumentPage.id,
            DocumentPage.document_id,
            DocumentPage.page_number,
            DocumentPage.text,
            rank,
            headline,
        )
        .join(Document, Document.id == DocumentPage.document_id)
        .where(DocumentPage.search_vector.op("@@")(tsquery))
        .order_by(rank.desc())
        .limit(max(1, min(limit, 200)))
        .offset(max(0, offset))
    )
    stmt = apply_document_search_filters(
        stmt,
        _base_filters(
            owner_id=owner_id,
            folder_id=folder_id,
            folder_ids=folder_ids,
            include_trashed=include_trashed,
            filters=filters,
        ),
    )

    rows = await session.execute(stmt)
    return [
        PageSearchHit(
            page_id=row.id,
            document_id=row.document_id,
            page_number=row.page_number,
            rank=float(row.rank or 0.0),
            snippet=row.snippet or "",
            text=row.text,
        )
        for row in rows.all()
    ]


async def count_pages_matching(
    session: AsyncSession,
    query: str,
    *,
    filters: DocumentSearchFilters,
) -> int:
    cleaned = query.strip()
    if not cleaned:
        return 0
    tsquery = func.websearch_to_tsquery(_ENGLISH_CONFIG, cleaned)
    stmt = (
        select(func.count(DocumentPage.id))
        .join(Document, Document.id == DocumentPage.document_id)
        .where(DocumentPage.search_vector.op("@@")(tsquery))
    )
    stmt = apply_document_search_filters(stmt, filters)
    return int((await session.execute(stmt)).scalar_one())


def _join_search_parts(*parts: str | None) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


async def _document_tag_names(session: AsyncSession, document_id: uuid.UUID) -> list[str]:
    from lesspaper_ngl.models import DocumentTag

    result = await session.execute(
        select(Tag.name)
        .join(DocumentTag, DocumentTag.tag_id == Tag.id)
        .where(DocumentTag.document_id == document_id)
    )
    return [name for (name,) in result.all()]
