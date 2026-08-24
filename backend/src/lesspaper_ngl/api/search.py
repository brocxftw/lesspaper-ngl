"""Search endpoints."""

from __future__ import annotations

import uuid
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.assignments import resolve_assignment
from lesspaper_ngl.ai.registry import get_adapter
from lesspaper_ngl.api.schemas import (
    DocumentOut,
    SearchHit,
    SearchMatch,
    SearchRequest,
    SearchResponse,
    SemanticCoverage,
)
from lesspaper_ngl.auth.deps import CurrentUser
from lesspaper_ngl.bootstrap import ensure_ai_settings
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.models import AIWorkloadRole
from lesspaper_ngl.search.filters import DocumentSearchFilters
from lesspaper_ngl.search.fts import (
    count_documents_matching,
    count_pages_matching,
    search_documents,
    search_pages,
)
from lesspaper_ngl.search.hybrid import hybrid_search
from lesspaper_ngl.search.semantic import (
    count_embedded_documents,
    count_searchable_documents,
    search_chunks_semantic,
)
from lesspaper_ngl.services import documents as doc_service
from lesspaper_ngl.services import folders as folder_service

router = APIRouter(prefix="/api/search", tags=["search"])

_MAX_MATCHES_PER_DOC = 5
_RAW_FETCH_CAP = 200


async def _resolve_folder_ids(
    db: AsyncSession,
    folder_id: uuid.UUID | None,
    folder_ids: list[uuid.UUID] | None,
    include_descendants: bool,
    owner_id: uuid.UUID,
) -> list[uuid.UUID] | None:
    if folder_ids:
        for candidate_id in folder_ids:
            await folder_service.get_folder(db, candidate_id, owner_id=owner_id)
        return folder_ids
    if folder_id is None:
        return None
    await folder_service.get_folder(db, folder_id, owner_id=owner_id)
    if include_descendants:
        return await folder_service.descendant_ids(
            db,
            folder_id,
            owner_id=owner_id,
        )
    return [folder_id]


def _filters_from_body(
    body: SearchRequest,
    *,
    owner_id: uuid.UUID,
    resolved_folder_ids: list[uuid.UUID] | None,
) -> DocumentSearchFilters:
    return DocumentSearchFilters(
        owner_id=owner_id,
        folder_ids=resolved_folder_ids,
        inbox=body.inbox,
        tag_ids=body.tag_ids,
        document_type_id=body.document_type_id,
        correspondent_id=body.correspondent_id,
        mime_type=body.mime_type,
        is_archived=body.is_archived,
        date_from=body.date_from,
        date_to=body.date_to,
        document_indexed=body.document_indexed,
        has_embeddings=body.has_embeddings,
        unprocessed=body.unprocessed,
    )


def _snippet_text(text: str | None, *, limit: int = 280) -> str | None:
    if not text:
        return None
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


async def _build_groups(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    ordered_doc_ids: list[uuid.UUID],
    scores: dict[uuid.UUID, float],
    matches_by_doc: dict[uuid.UUID, list[SearchMatch]],
) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for doc_id in ordered_doc_ids:
        doc = await doc_service.get_document(db, doc_id, owner_id=owner_id)
        matches = sorted(
            matches_by_doc.get(doc_id, []),
            key=lambda m: m.score,
            reverse=True,
        )[:_MAX_MATCHES_PER_DOC]
        best = matches[0] if matches else None
        hits.append(
            SearchHit(
                document=DocumentOut.model_validate(doc_service.document_to_dict(doc)),
                score=scores.get(doc_id, best.score if best else 0.0),
                snippet=best.snippet if best else None,
                page_number=best.page_number if best else None,
                chunk_id=best.chunk_id if best else None,
                matches=matches,
            )
        )
    return hits


def _paginate_doc_ids(
    ordered_ids: list[uuid.UUID],
    *,
    page: int,
    page_size: int,
) -> list[uuid.UUID]:
    start = (page - 1) * page_size
    return ordered_ids[start : start + page_size]


@router.post("", response_model=SearchResponse)
async def search(
    body: SearchRequest,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SearchResponse:
    return await execute_search(db, _user.id, body)


async def execute_search(
    db: AsyncSession,
    owner_id: uuid.UUID,
    body: SearchRequest,
) -> SearchResponse:
    ai_settings = await ensure_ai_settings(db)
    semantic_available = False
    query_embedding: list[float] | None = None
    embed_provider_name: str | None = None
    embed_model: str | None = None
    embed_dim: int | None = None

    embedding = await resolve_assignment(db, AIWorkloadRole.EMBEDDING)
    if embedding.provider is not None:
        provider = embedding.provider
        if provider.enabled and embedding.model:
            semantic_available = True
            embed_provider_name = ai_settings.active_embedding_provider or provider.name
            embed_model = ai_settings.active_embedding_model or embedding.model
            embed_dim = ai_settings.active_embedding_dimension
            if body.mode in {"semantic", "hybrid"} and body.query.strip():
                adapter = get_adapter(provider)
                try:
                    result = await adapter.embed([body.query], model=embed_model)
                    if result.embeddings:
                        query_embedding = result.embeddings[0]
                        if embed_dim is None and query_embedding:
                            embed_dim = len(query_embedding)
                finally:
                    await adapter.aclose()

    resolved_folder_ids = await _resolve_folder_ids(
        db,
        body.folder_id,
        body.folder_ids,
        body.include_descendants,
        owner_id,
    )
    filters = _filters_from_body(
        body,
        owner_id=owner_id,
        resolved_folder_ids=resolved_folder_ids,
    )

    coverage: SemanticCoverage | None = None
    if semantic_available and embed_provider_name and embed_model and embed_dim:
        embedded = await count_embedded_documents(
            db,
            filters=filters,
            embedding_provider=embed_provider_name,
            embedding_model=embed_model,
            embedding_dimension=embed_dim,
        )
        searchable = await count_searchable_documents(db, filters=filters)
        coverage = SemanticCoverage(
            available=True,
            embedded_documents=embedded,
            searchable_documents=searchable,
            partial=searchable > 0 and embedded < searchable,
        )
    elif not semantic_available:
        coverage = SemanticCoverage(available=False, partial=False)

    effective_mode = body.mode
    matches_by_doc: dict[uuid.UUID, list[SearchMatch]] = defaultdict(list)
    scores: dict[uuid.UUID, float] = {}
    ordered_ids: list[uuid.UUID] = []
    document_total = 0
    match_total = 0

    use_keyword = body.mode == "keyword" or (
        body.mode in {"hybrid", "semantic"} and not query_embedding
    )
    if use_keyword and body.mode != "keyword":
        effective_mode = "keyword"

    if use_keyword:
        page_hits = await search_pages(
            db,
            body.query,
            owner_id=owner_id,
            filters=filters,
            limit=_RAW_FETCH_CAP,
        )
        doc_hits = await search_documents(
            db,
            body.query,
            owner_id=owner_id,
            filters=filters,
            limit=_RAW_FETCH_CAP,
        )
        match_total = await count_pages_matching(db, body.query, filters=filters)
        document_total = await count_documents_matching(db, body.query, filters=filters)

        for hit in page_hits:
            matches_by_doc[hit.document_id].append(
                SearchMatch(
                    kind="page",
                    score=hit.rank,
                    snippet=hit.snippet or _snippet_text(hit.text),
                    page_number=hit.page_number,
                )
            )
            scores[hit.document_id] = max(scores.get(hit.document_id, 0.0), hit.rank)

        for hit in doc_hits:
            if hit.document_id not in matches_by_doc:
                matches_by_doc[hit.document_id].append(
                    SearchMatch(
                        kind="document",
                        score=hit.rank,
                        snippet=hit.snippet,
                    )
                )
            scores[hit.document_id] = max(scores.get(hit.document_id, 0.0), hit.rank)

        ordered_ids = sorted(scores.keys(), key=lambda d: scores[d], reverse=True)
        if match_total == 0:
            match_total = document_total

    elif (
        body.mode == "semantic"
        and query_embedding
        and embed_provider_name
        and embed_model
        and embed_dim
    ):
        sem_hits = await search_chunks_semantic(
            db,
            query_embedding,
            owner_id=owner_id,
            embedding_provider=embed_provider_name,
            embedding_model=embed_model,
            embedding_dimension=embed_dim,
            filters=filters,
            limit=_RAW_FETCH_CAP,
        )
        match_total = len(sem_hits)
        for hit in sem_hits:
            matches_by_doc[hit.document_id].append(
                SearchMatch(
                    kind="chunk",
                    score=hit.score,
                    snippet=_snippet_text(hit.text),
                    page_number=hit.page_number,
                    chunk_id=hit.chunk_id,
                )
            )
            scores[hit.document_id] = max(scores.get(hit.document_id, 0.0), hit.score)
        ordered_ids = sorted(scores.keys(), key=lambda d: scores[d], reverse=True)
        document_total = len(ordered_ids)
        effective_mode = "semantic"

    elif (
        body.mode == "hybrid"
        and query_embedding
        and embed_provider_name
        and embed_model
        and embed_dim
    ):
        hybrid_hits = await hybrid_search(
            db,
            body.query,
            query_embedding,
            owner_id=owner_id,
            embedding_provider=embed_provider_name,
            embedding_model=embed_model,
            embedding_dimension=embed_dim,
            filters=filters,
            limit=_RAW_FETCH_CAP,
            keyword_limit=80,
            vector_limit=80,
        )
        match_total = len(hybrid_hits)
        for hit in hybrid_hits:
            kind = "chunk" if hit.chunk_id else ("page" if hit.page_number else "document")
            matches_by_doc[hit.document_id].append(
                SearchMatch(
                    kind=kind,  # type: ignore[arg-type]
                    score=hit.score,
                    snippet=_snippet_text(hit.text)
                    if hit.text and "<" not in (hit.text or "")
                    else hit.text,
                    page_number=hit.page_number,
                    chunk_id=hit.chunk_id,
                )
            )
            scores[hit.document_id] = max(scores.get(hit.document_id, 0.0), hit.score)
        ordered_ids = sorted(scores.keys(), key=lambda d: scores[d], reverse=True)
        document_total = len(ordered_ids)
        # Prefer FTS document count when keyword contributed.
        fts_docs = await count_documents_matching(db, body.query, filters=filters)
        if fts_docs > document_total:
            document_total = fts_docs
        effective_mode = "hybrid"

    else:
        # Empty / unexpected fallback
        effective_mode = "keyword"

    page_ids = _paginate_doc_ids(ordered_ids, page=body.page, page_size=body.page_size)
    items = await _build_groups(
        db,
        owner_id=owner_id,
        ordered_doc_ids=page_ids,
        scores=scores,
        matches_by_doc=matches_by_doc,
    )

    return SearchResponse(
        items=items,
        total=document_total,
        document_total=document_total,
        match_total=match_total,
        mode=body.mode,
        effective_mode=effective_mode,
        semantic_available=semantic_available,
        semantic_coverage=coverage,
    )
