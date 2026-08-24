"""Resolve evidence-search document IDs for Ask/RAG scopes."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.base import AIProviderAdapter
from lesspaper_ngl.search.filters import DocumentSearchFilters
from lesspaper_ngl.search.fts import search_documents, search_pages
from lesspaper_ngl.search.hybrid import hybrid_search
from lesspaper_ngl.search.semantic import search_chunks_semantic
from lesspaper_ngl.services import folders as folder_service

SearchMode = Literal["keyword", "semantic", "hybrid"]

_RAW_FETCH_CAP = 200


@dataclass(frozen=True)
class EvidenceSearchParams:
    query: str
    mode: SearchMode = "hybrid"
    folder_id: uuid.UUID | None = None
    include_descendants: bool = True
    folder_ids: list[uuid.UUID] | None = None
    tag_ids: list[uuid.UUID] | None = None
    document_type_id: uuid.UUID | None = None
    correspondent_id: uuid.UUID | None = None
    mime_type: str | None = None
    is_archived: bool | None = None
    inbox: bool | None = None
    date_from: date | None = None
    date_to: date | None = None
    document_indexed: bool | None = None
    has_embeddings: bool | None = None
    unprocessed: bool | None = None


async def _resolve_folder_ids(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    folder_id: uuid.UUID | None,
    folder_ids: list[uuid.UUID] | None,
    include_descendants: bool,
) -> list[uuid.UUID] | None:
    if folder_ids:
        for candidate_id in folder_ids:
            await folder_service.get_folder(session, candidate_id, owner_id=owner_id)
        return folder_ids
    if folder_id is None:
        return None
    await folder_service.get_folder(session, folder_id, owner_id=owner_id)
    if include_descendants:
        return await folder_service.descendant_ids(
            session,
            folder_id,
            owner_id=owner_id,
        )
    return [folder_id]


async def resolve_evidence_document_ids(
    session: AsyncSession,
    params: EvidenceSearchParams,
    *,
    owner_id: uuid.UUID,
    embed_adapter: AIProviderAdapter | None = None,
    embedding_provider: str | None = None,
    embedding_model: str | None = None,
    embedding_dimension: int | None = None,
    limit: int = _RAW_FETCH_CAP,
) -> list[uuid.UUID]:
    """Return distinct document IDs matching an evidence-search snapshot."""
    query = params.query.strip()
    if not query:
        return []

    resolved_folder_ids = await _resolve_folder_ids(
        session,
        owner_id=owner_id,
        folder_id=params.folder_id,
        folder_ids=params.folder_ids,
        include_descendants=params.include_descendants,
    )
    filters = DocumentSearchFilters(
        owner_id=owner_id,
        folder_ids=resolved_folder_ids,
        inbox=params.inbox,
        tag_ids=params.tag_ids,
        document_type_id=params.document_type_id,
        correspondent_id=params.correspondent_id,
        mime_type=params.mime_type,
        is_archived=params.is_archived,
        date_from=params.date_from,
        date_to=params.date_to,
        document_indexed=params.document_indexed,
        has_embeddings=params.has_embeddings,
        unprocessed=params.unprocessed,
    )

    mode = params.mode
    query_embedding: list[float] | None = None
    if (
        mode in {"semantic", "hybrid"}
        and embed_adapter is not None
        and embedding_model
        and embedding_dimension
    ):
        result = await embed_adapter.embed([query], model=embedding_model)
        if result.embeddings:
            query_embedding = result.embeddings[0]

    scores: dict[uuid.UUID, float] = {}

    if mode == "keyword" or (mode in {"hybrid", "semantic"} and not query_embedding):
        page_hits = await search_pages(
            session,
            query,
            owner_id=owner_id,
            filters=filters,
            limit=limit,
        )
        doc_hits = await search_documents(
            session,
            query,
            owner_id=owner_id,
            filters=filters,
            limit=limit,
        )
        for hit in page_hits:
            scores[hit.document_id] = max(scores.get(hit.document_id, 0.0), hit.rank)
        for hit in doc_hits:
            scores[hit.document_id] = max(scores.get(hit.document_id, 0.0), hit.rank)
    elif mode == "semantic" and query_embedding and embedding_provider and embedding_model and embedding_dimension:
        sem_hits = await search_chunks_semantic(
            session,
            query_embedding,
            owner_id=owner_id,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
            filters=filters,
            limit=limit,
        )
        for hit in sem_hits:
            scores[hit.document_id] = max(scores.get(hit.document_id, 0.0), hit.score)
    elif mode == "hybrid" and query_embedding and embedding_provider and embedding_model and embedding_dimension:
        hybrid_hits = await hybrid_search(
            session,
            query,
            query_embedding,
            owner_id=owner_id,
            embedding_provider=embedding_provider,
            embedding_model=embedding_model,
            embedding_dimension=embedding_dimension,
            filters=filters,
            limit=limit,
        )
        for hit in hybrid_hits:
            scores[hit.document_id] = max(scores.get(hit.document_id, 0.0), hit.score)
    else:
        doc_hits = await search_documents(
            session,
            query,
            owner_id=owner_id,
            filters=filters,
            limit=limit,
        )
        for hit in doc_hits:
            scores[hit.document_id] = max(scores.get(hit.document_id, 0.0), hit.rank)

    return sorted(scores.keys(), key=lambda d: scores[d], reverse=True)
