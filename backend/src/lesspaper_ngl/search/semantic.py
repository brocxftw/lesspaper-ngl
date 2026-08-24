"""Semantic chunk search using pgvector."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.embeddings import pad_embedding
from lesspaper_ngl.models import Document, DocumentChunk
from lesspaper_ngl.search.filters import DocumentSearchFilters, apply_document_search_filters


@dataclass(frozen=True)
class SemanticHit:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    page_number: int | None
    section: str | None
    text: str
    score: float
    chunk_index: int


async def search_chunks_semantic(
    session: AsyncSession,
    query_embedding: list[float],
    *,
    owner_id: uuid.UUID,
    embedding_provider: str,
    embedding_model: str,
    embedding_dimension: int,
    limit: int = 20,
    document_ids: list[uuid.UUID] | None = None,
    folder_id: uuid.UUID | None = None,
    folder_ids: list[uuid.UUID] | None = None,
    include_trashed: bool = False,
    filters: DocumentSearchFilters | None = None,
) -> list[SemanticHit]:
    """Cosine similarity search over document chunks in a specific embedding space."""
    if not query_embedding:
        return []
    if len(query_embedding) != embedding_dimension:
        raise ValueError(
            f"Query embedding dimension {len(query_embedding)} "
            f"does not match expected {embedding_dimension}"
        )

    storage_query = pad_embedding(query_embedding)
    distance = DocumentChunk.embedding.cosine_distance(storage_query)
    score = (1 - distance).label("score")

    stmt = (
        select(
            DocumentChunk.id,
            DocumentChunk.document_id,
            DocumentChunk.page_number,
            DocumentChunk.section,
            DocumentChunk.text,
            DocumentChunk.chunk_index,
            score,
        )
        .join(Document, Document.id == DocumentChunk.document_id)
        .where(
            DocumentChunk.embedding.isnot(None),
            DocumentChunk.embedding_provider == embedding_provider,
            DocumentChunk.embedding_model == embedding_model,
            DocumentChunk.embedding_dimension == embedding_dimension,
        )
        .order_by(distance.asc())
        .limit(max(1, min(limit, 200)))
    )

    if document_ids:
        stmt = stmt.where(DocumentChunk.document_id.in_(document_ids))

    filt = filters or DocumentSearchFilters(
        owner_id=owner_id,
        folder_id=folder_id,
        folder_ids=folder_ids,
        include_trashed=include_trashed,
    )
    stmt = apply_document_search_filters(stmt, filt)

    rows = await session.execute(stmt)
    return [
        SemanticHit(
            chunk_id=row.id,
            document_id=row.document_id,
            page_number=row.page_number,
            section=row.section,
            text=row.text,
            score=float(row.score or 0.0),
            chunk_index=row.chunk_index,
        )
        for row in rows.all()
    ]


async def count_embedded_documents(
    session: AsyncSession,
    *,
    filters: DocumentSearchFilters,
    embedding_provider: str,
    embedding_model: str,
    embedding_dimension: int,
) -> int:
    stmt = (
        select(func.count(func.distinct(Document.id)))
        .join(DocumentChunk, DocumentChunk.document_id == Document.id)
        .where(
            DocumentChunk.embedding.isnot(None),
            DocumentChunk.embedding_provider == embedding_provider,
            DocumentChunk.embedding_model == embedding_model,
            DocumentChunk.embedding_dimension == embedding_dimension,
        )
    )
    stmt = apply_document_search_filters(stmt, filters)
    return int((await session.execute(stmt)).scalar_one())


async def count_searchable_documents(
    session: AsyncSession,
    *,
    filters: DocumentSearchFilters,
) -> int:
    stmt = select(func.count(Document.id))
    stmt = apply_document_search_filters(stmt, filters)
    return int((await session.execute(stmt)).scalar_one())
