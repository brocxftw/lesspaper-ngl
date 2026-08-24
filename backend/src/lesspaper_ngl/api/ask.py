"""Workspace-wide ask / RAG endpoint."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.assignments import resolve_assignment
from lesspaper_ngl.ai.rag import RAGScope
from lesspaper_ngl.ai.rag import ask as rag_ask
from lesspaper_ngl.ai.registry import get_adapter
from lesspaper_ngl.api.schemas import AskRequest, AskResponse, CitationOut
from lesspaper_ngl.auth.deps import CurrentUser, SafeSession
from lesspaper_ngl.bootstrap import ensure_ai_settings
from lesspaper_ngl.core.exceptions import PrivacyViolationError, ValidationError
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.models import AIWorkloadRole
from lesspaper_ngl.search.resolve import EvidenceSearchParams, resolve_evidence_document_ids

router = APIRouter(prefix="/api/ask", tags=["ask"])


@router.post("", response_model=AskResponse)
async def ask_workspace(
    body: AskRequest,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AskResponse:
    settings_row = await ensure_ai_settings(db)
    chat = await resolve_assignment(db, AIWorkloadRole.CHAT)
    if chat.provider is None or not chat.model:
        raise ValidationError("No chat provider configured")

    chat_provider = chat.provider
    if not chat_provider.enabled:
        raise ValidationError("Chat provider is not available")

    if settings_row.warn_before_remote and not chat_provider.is_local and not body.confirm_remote:
        raise PrivacyViolationError("Remote AI usage requires confirm_remote=true")

    embed_adapter = None
    embed_provider = None
    embedding = await resolve_assignment(db, AIWorkloadRole.EMBEDDING)
    if embedding.provider is not None:
        embed_provider = embedding.provider
        if embed_provider.enabled and embedding.model:
            embed_adapter = get_adapter(embed_provider)

    scope = RAGScope(
        kind=body.scope,
        document_id=body.document_id,
        document_ids=body.document_ids or [],
        folder_id=body.folder_id,
        search_query=body.search_query,
    )

    # Typed search snapshot → concrete document IDs (preserves mode + filters).
    if body.scope == "search":
        snapshot = body.search
        query = (snapshot.query if snapshot else body.search_query) or ""
        if not query.strip():
            raise ValidationError("search scope requires search snapshot or search_query")
        params = EvidenceSearchParams(
            query=query.strip(),
            mode=(snapshot.mode if snapshot else "hybrid"),
            folder_id=snapshot.folder_id if snapshot else None,
            include_descendants=snapshot.include_descendants if snapshot else True,
            folder_ids=snapshot.folder_ids if snapshot else None,
            tag_ids=snapshot.tag_ids if snapshot else None,
            document_type_id=snapshot.document_type_id if snapshot else None,
            correspondent_id=snapshot.correspondent_id if snapshot else None,
            mime_type=snapshot.mime_type if snapshot else None,
            is_archived=snapshot.is_archived if snapshot else None,
            inbox=snapshot.inbox if snapshot else None,
            date_from=snapshot.date_from if snapshot else None,
            date_to=snapshot.date_to if snapshot else None,
            document_indexed=snapshot.document_indexed if snapshot else None,
            has_embeddings=snapshot.has_embeddings if snapshot else None,
            unprocessed=snapshot.unprocessed if snapshot else None,
        )
        embed_provider_name = None
        embed_model = None
        embed_dim = None
        if embed_provider is not None and embed_adapter is not None:
            embed_provider_name = settings_row.active_embedding_provider or embed_provider.name
            embed_model = settings_row.active_embedding_model or embedding.model
            embed_dim = settings_row.active_embedding_dimension
        doc_ids = await resolve_evidence_document_ids(
            db,
            params,
            owner_id=_user.id,
            embed_adapter=embed_adapter,
            embedding_provider=embed_provider_name,
            embedding_model=embed_model,
            embedding_dimension=embed_dim,
        )
        scope = RAGScope(kind="documents", document_ids=doc_ids)

    result = await rag_ask(
        db,
        owner_id=_user.id,
        question=body.question,
        settings=settings_row,
        chat_provider=chat_provider,
        chat_adapter=get_adapter(chat_provider),
        chat_model=chat.model,
        scope=scope,
        embed_adapter=embed_adapter,
        embedding_model=embedding.model,
        embedding_provider=embed_provider.name if embed_provider else None,
    )

    return AskResponse(
        answer=result.answer,
        citations=[
            CitationOut(
                document_id=c.document_id,
                page_number=c.page_number,
                chunk_id=c.chunk_id,
                title=c.title,
                quote=c.quote,
            )
            for c in result.citations
        ],
        passages=[
            CitationOut(
                document_id=c.document_id,
                page_number=c.page_number,
                chunk_id=c.chunk_id,
                title=c.title,
                quote=c.quote,
            )
            for c in result.passages
        ],
        provider=result.provider,
        model=result.model,
        privacy_mode=settings_row.privacy_mode.value,
        is_local=chat_provider.is_local,
        insufficient_evidence=result.insufficient_evidence,
    )
