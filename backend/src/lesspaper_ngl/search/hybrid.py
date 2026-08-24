"""Hybrid retrieval combining keyword and vector search with RRF."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.search.fts import search_documents, search_pages
from lesspaper_ngl.search.semantic import search_chunks_semantic

DEFAULT_RRF_K = 60


@dataclass(frozen=True)
class HybridHit:
    document_id: uuid.UUID
    score: float
    chunk_id: uuid.UUID | None = None
    page_number: int | None = None
    text: str | None = None
    title: str | None = None
    sources: dict[str, int] = field(default_factory=dict)


async def hybrid_search(
    session: AsyncSession,
    query: str,
    query_embedding: list[float],
    *,
    owner_id: uuid.UUID,
    embedding_provider: str,
    embedding_model: str,
    embedding_dimension: int,
    folder_id: uuid.UUID | None = None,
    folder_ids: list[uuid.UUID] | None = None,
    include_trashed: bool = False,
    filters=None,
    limit: int = 20,
    keyword_limit: int = 40,
    vector_limit: int = 40,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[HybridHit]:
    """Merge keyword and semantic results using reciprocal rank fusion."""
    keyword_hits = await search_pages(
        session,
        query,
        owner_id=owner_id,
        folder_id=folder_id,
        folder_ids=folder_ids,
        include_trashed=include_trashed,
        filters=filters,
        limit=keyword_limit,
    )
    vector_hits = await search_chunks_semantic(
        session,
        query_embedding,
        owner_id=owner_id,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        folder_id=folder_id,
        folder_ids=folder_ids,
        include_trashed=include_trashed,
        filters=filters,
        limit=vector_limit,
    )

    if not keyword_hits and not vector_hits:
        return []

    doc_titles = await _document_titles(
        session,
        {hit.document_id for hit in keyword_hits} | {hit.document_id for hit in vector_hits},
    )

    fused: dict[str, _FusionEntry] = {}

    for rank, hit in enumerate(keyword_hits, start=1):
        key = _fusion_key(hit.document_id, page_number=hit.page_number)
        entry = fused.setdefault(key, _FusionEntry(document_id=hit.document_id))
        entry.score += 1.0 / (rrf_k + rank)
        entry.sources["keyword"] = rank
        entry.page_number = hit.page_number
        entry.text = hit.snippet or hit.text
        entry.title = doc_titles.get(hit.document_id)

    for rank, hit in enumerate(vector_hits, start=1):
        key = _fusion_key(hit.document_id, chunk_id=hit.chunk_id)
        entry = fused.setdefault(key, _FusionEntry(document_id=hit.document_id))
        entry.score += 1.0 / (rrf_k + rank)
        entry.sources["vector"] = rank
        entry.chunk_id = hit.chunk_id
        entry.page_number = hit.page_number or entry.page_number
        entry.text = hit.text
        entry.title = doc_titles.get(hit.document_id)

    # Boost documents that appear in document-level keyword search.
    doc_keyword = await search_documents(
        session,
        query,
        owner_id=owner_id,
        folder_id=folder_id,
        folder_ids=folder_ids,
        include_trashed=include_trashed,
        filters=filters,
        limit=min(keyword_limit, 20),
    )
    for rank, hit in enumerate(doc_keyword, start=1):
        key = _fusion_key(hit.document_id)
        entry = fused.setdefault(key, _FusionEntry(document_id=hit.document_id))
        entry.score += 0.5 / (rrf_k + rank)
        entry.sources["document_keyword"] = rank
        entry.title = hit.title
        entry.text = entry.text or hit.snippet

    ordered = sorted(fused.values(), key=lambda item: item.score, reverse=True)
    return [
        HybridHit(
            document_id=item.document_id,
            score=item.score,
            chunk_id=item.chunk_id,
            page_number=item.page_number,
            text=item.text,
            title=item.title,
            sources=dict(item.sources),
        )
        for item in ordered[: max(1, min(limit, 200))]
    ]


@dataclass
class _FusionEntry:
    document_id: uuid.UUID
    score: float = 0.0
    chunk_id: uuid.UUID | None = None
    page_number: int | None = None
    text: str | None = None
    title: str | None = None
    sources: dict[str, int] = field(default_factory=dict)


def _fusion_key(
    document_id: uuid.UUID,
    *,
    chunk_id: uuid.UUID | None = None,
    page_number: int | None = None,
) -> str:
    if chunk_id is not None:
        return f"chunk:{chunk_id}"
    if page_number is not None:
        return f"page:{document_id}:{page_number}"
    return f"doc:{document_id}"


async def _document_titles(
    session: AsyncSession,
    document_ids: set[uuid.UUID],
) -> dict[uuid.UUID, str]:
    if not document_ids:
        return {}
    from sqlalchemy import select

    from lesspaper_ngl.models import Document

    result = await session.execute(
        select(Document.id, Document.title).where(Document.id.in_(document_ids))
    )
    return {row.id: row.title for row in result.all()}


def reciprocal_rank_fusion(
    ranked_lists: list[list[uuid.UUID]],
    *,
    rrf_k: int = DEFAULT_RRF_K,
) -> list[tuple[uuid.UUID, float]]:
    """Pure RRF helper for tests and offline merging."""
    scores: dict[uuid.UUID, float] = {}
    for ranked in ranked_lists:
        for rank, item_id in enumerate(ranked, start=1):
            scores[item_id] = scores.get(item_id, 0.0) + 1.0 / (rrf_k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
