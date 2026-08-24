"""Document management endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from lesspaper_ngl.ai.assignments import resolve_assignment
from lesspaper_ngl.ai.profiles import resolve_profile
from lesspaper_ngl.ai.rag import RAGScope
from lesspaper_ngl.ai.rag import ask as rag_ask
from lesspaper_ngl.ai.registry import get_adapter
from lesspaper_ngl.api.schemas import (
    AskCitationSnapshotOut,
    AskConversationOut,
    AskMessageOut,
    AskRequest,
    AskResponse,
    BulkActionRequest,
    CitationOut,
    DocumentContentOut,
    DocumentListOut,
    DocumentMetadataUpdate,
    DocumentMoveRequest,
    DocumentOut,
    DocumentPageContentOut,
    DocumentProcessRequest,
    DocumentProcessResultOut,
    DocumentRemoveQueueRequest,
    MessageOut,
    UploadResultOut,
)
from lesspaper_ngl.auth.deps import CurrentUser, SafeSession
from lesspaper_ngl.bootstrap import ensure_ai_settings
from lesspaper_ngl.core.exceptions import NotFoundError, PrivacyViolationError, ValidationError
from lesspaper_ngl.db.session import get_db
from lesspaper_ngl.models import AIWorkloadRole, DocumentPage, Tag
from lesspaper_ngl.services import ask_conversations as ask_conv_service
from lesspaper_ngl.services import documents as doc_service
from lesspaper_ngl.services import folders as folder_service
from lesspaper_ngl.storage.service import StorageService

router = APIRouter(tags=["documents"])


def _doc_out(doc) -> DocumentOut:
    return DocumentOut.model_validate(doc_service.document_to_dict(doc))


async def _resolve_ai_for_ask(db: AsyncSession, confirm_remote: bool):
    settings_row = await ensure_ai_settings(db)
    chat = await resolve_assignment(db, AIWorkloadRole.CHAT)
    if chat.provider is None or not chat.model:
        raise ValidationError("No chat provider configured")

    chat_provider = chat.provider
    if not chat_provider.enabled:
        raise ValidationError("Chat provider is not available")

    if settings_row.warn_before_remote and not chat_provider.is_local and not confirm_remote:
        raise PrivacyViolationError("Remote AI usage requires confirm_remote=true")

    embed_adapter = None
    embed_model = None
    embed_provider_name = None
    embedding = await resolve_assignment(db, AIWorkloadRole.EMBEDDING)
    if embedding.provider is not None:
        embed_provider = embedding.provider
        if embed_provider.enabled and embedding.model:
            embed_adapter = get_adapter(embed_provider)
            embed_model = embedding.model
            embed_provider_name = embed_provider.name

    return (
        settings_row,
        chat_provider,
        chat.model,
        get_adapter(chat_provider),
        embed_adapter,
        embed_model,
        embed_provider_name,
    )


@router.get("/api/documents", response_model=DocumentListOut)
async def list_documents(
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    folder_id: uuid.UUID | None = None,
    include_descendants: bool = False,
    inbox: bool | None = None,
    inbox_status: Literal["preparing", "ready", "needs_review", "failed"] | None = None,
    trashed: bool = False,
    unprocessed: bool | None = None,
    tag_ids: Annotated[list[uuid.UUID] | None, Query()] = None,
    q: str | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    sort: str = "added_date",
    order: str = "desc",
) -> DocumentListOut:
    items, total = await doc_service.list_documents(
        db,
        owner_id=_user.id,
        folder_id=folder_id,
        include_descendants=include_descendants,
        inbox=inbox,
        inbox_status=inbox_status,
        trashed=trashed,
        unprocessed=unprocessed,
        tag_ids=tag_ids,
        q=q,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return DocumentListOut(
        items=[_doc_out(d) for d in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/api/folders/{folder_id}/documents", response_model=DocumentListOut)
async def list_folder_documents(
    folder_id: uuid.UUID,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_descendants: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    sort: str = "added_date",
    order: str = "desc",
) -> DocumentListOut:
    await folder_service.get_folder(db, folder_id, owner_id=_user.id)
    items, total = await doc_service.list_documents(
        db,
        owner_id=_user.id,
        folder_id=folder_id,
        include_descendants=include_descendants,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
    )
    return DocumentListOut(
        items=[_doc_out(d) for d in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post(
    "/api/documents/upload",
    response_model=None,
    status_code=201,
    responses={
        201: {"model": DocumentOut},
        200: {"model": UploadResultOut},
    },
)
async def upload_document(
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File()],
    folder_id: Annotated[uuid.UUID | None, Form()] = None,
    relative_path: Annotated[str | None, Form()] = None,
    on_duplicate: Annotated[Literal["error", "skip"], Form()] = "error",
) -> DocumentOut | UploadResultOut:
    """Upload a single file.

    Optional ``relative_path`` (e.g. ``Finance/2024/invoice.pdf``) recreates
    intermediate lesspaper-ngl folders under ``folder_id``. When ``folder_id`` is
    omitted, the file enters Inbox with that path stored as a pending folder
    target (materialized when the document is processed).

    Duplicate handling is content-based (SHA-256):
    - ``on_duplicate=error`` (default): HTTP 409
    - ``on_duplicate=skip``: HTTP 200 with ``status=duplicate`` (no second blob)
    """
    data = await file.read()
    storage = StorageService()
    result = await doc_service.ingest_bytes(
        db,
        owner_id=_user.id,
        data=data,
        filename=file.filename or "document",
        folder_id=folder_id,
        relative_path=relative_path,
        on_duplicate=on_duplicate,
        storage=storage,
    )
    if result.status == "duplicate":
        body = UploadResultOut(
            status="duplicate",
            duplicate=True,
            existing_document_id=uuid.UUID(result.existing_document_id),
            message="Document already exists (same content checksum)",
            relative_path=result.relative_path,
        )
        return JSONResponse(status_code=200, content=body.model_dump(mode="json"))
    assert result.document is not None
    return _doc_out(result.document)


@router.get("/api/documents/{document_id}", response_model=DocumentOut)
async def get_document(
    document_id: uuid.UUID,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentOut:
    doc = await doc_service.get_document(db, document_id, owner_id=_user.id)
    return _doc_out(doc)


@router.patch("/api/documents/{document_id}/metadata", response_model=DocumentOut)
async def update_metadata(
    document_id: uuid.UUID,
    body: DocumentMetadataUpdate,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentOut:
    data = body.model_dump(exclude_unset=True)
    doc = await doc_service.update_metadata(db, document_id, data, owner_id=_user.id)
    return _doc_out(doc)


@router.post("/api/documents/process", response_model=DocumentProcessResultOut)
async def process_documents(
    body: DocumentProcessRequest,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentProcessResultOut:
    result = await doc_service.process_inbox_documents(
        db,
        body.document_ids,
        owner_id=_user.id,
    )
    return DocumentProcessResultOut(**result)


@router.post("/api/documents/remove-from-queue", response_model=MessageOut)
async def remove_documents_from_queue(
    body: DocumentRemoveQueueRequest,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    storage = StorageService()
    removed = 0
    for doc_id in body.document_ids:
        await doc_service.remove_from_queue(db, doc_id, owner_id=_user.id, storage=storage)
        removed += 1
    return MessageOut(message=f"Removed {removed} document(s) from the queue")


@router.post("/api/documents/{document_id}/remove-from-queue", response_model=MessageOut)
async def remove_document_from_queue(
    document_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    await doc_service.remove_from_queue(
        db, document_id, owner_id=_user.id, storage=StorageService()
    )
    return MessageOut(message="Removed from queue")


@router.post("/api/documents/{document_id}/retry-preflight", response_model=DocumentOut)
async def retry_preflight(
    document_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentOut:
    doc = await doc_service.retry_preflight(db, document_id, owner_id=_user.id)
    return _doc_out(doc)


@router.post("/api/documents/{document_id}/retry-ocr", response_model=DocumentOut)
async def retry_ocr(
    document_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentOut:
    doc = await doc_service.retry_ocr(db, document_id, owner_id=_user.id)
    return _doc_out(doc)


@router.post("/api/documents/{document_id}/reprocess-embeddings", response_model=DocumentOut)
async def reprocess_embeddings(
    document_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentOut:
    doc = await doc_service.reprocess_embeddings(db, document_id, owner_id=_user.id)
    return _doc_out(doc)


@router.post("/api/documents/{document_id}/reprocess-suggestions", response_model=DocumentOut)
async def reprocess_suggestions(
    document_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentOut:
    doc = await doc_service.reprocess_suggestions(db, document_id, owner_id=_user.id)
    return _doc_out(doc)


@router.post("/api/documents/{document_id}/move", response_model=DocumentOut)
async def move_document(
    document_id: uuid.UUID,
    body: DocumentMoveRequest,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentOut:
    doc = await doc_service.move_document(db, document_id, body.folder_id, owner_id=_user.id)
    return _doc_out(doc)


@router.post("/api/documents/{document_id}/trash", response_model=DocumentOut)
async def trash_document(
    document_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentOut:
    doc = await doc_service.trash_document(db, document_id, owner_id=_user.id)
    return _doc_out(doc)


@router.post("/api/documents/{document_id}/restore", response_model=DocumentOut)
async def restore_document(
    document_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    folder_id: uuid.UUID | None = None,
) -> DocumentOut:
    doc = await doc_service.restore_document(
        db,
        document_id,
        folder_id=folder_id,
        owner_id=_user.id,
    )
    return _doc_out(doc)


@router.delete("/api/documents/{document_id}", response_model=MessageOut)
async def delete_document(
    document_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    storage = StorageService()
    await doc_service.permanently_delete(
        db,
        document_id,
        owner_id=_user.id,
        storage=storage,
    )
    return MessageOut(message="Document permanently deleted")


@router.api_route(
    "/api/documents/{document_id}/download",
    methods=["GET", "HEAD"],
)
async def download_document(
    document_id: uuid.UUID,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    doc = await doc_service.get_document(db, document_id, owner_id=_user.id)
    storage = StorageService()
    path = storage.open_original_path(doc.storage_key)
    # inline so browsers/pdf.js can display; download attribute still forces save
    safe_name = doc.original_filename.replace('"', "")
    return FileResponse(
        path,
        media_type=doc.mime_type,
        filename=doc.original_filename,
        content_disposition_type="inline",
        headers={
            "Content-Disposition": f'inline; filename="{safe_name}"',
        },
    )


@router.get("/api/documents/{document_id}/thumbnail")
async def download_thumbnail(
    document_id: uuid.UUID,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FileResponse:
    doc = await doc_service.get_document(db, document_id, owner_id=_user.id)
    if not doc.thumbnail_key:
        raise NotFoundError("Thumbnail not available")
    storage = StorageService()
    path = storage.thumbnail_absolute(doc.thumbnail_key)
    if not path.exists():
        raise NotFoundError("Thumbnail file not found")
    return FileResponse(
        path,
        media_type="image/jpeg",
        filename=f"{doc.title}-thumb.jpg",
    )


@router.get("/api/documents/{document_id}/content", response_model=DocumentContentOut)
async def document_content(
    document_id: uuid.UUID,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentContentOut:
    doc = await doc_service.get_document(db, document_id, owner_id=_user.id)
    pages = (
        (
            await db.execute(
                select(DocumentPage)
                .where(DocumentPage.document_id == document_id)
                .order_by(DocumentPage.page_number)
            )
        )
        .scalars()
        .all()
    )
    return DocumentContentOut(
        document_id=doc.id,
        title=doc.title,
        page_count=doc.page_count or len(pages),
        pages=[DocumentPageContentOut(page_number=p.page_number, text=p.text) for p in pages],
    )


@router.get(
    "/api/documents/{document_id}/ask/conversation",
    response_model=AskConversationOut,
)
async def get_ask_conversation(
    document_id: uuid.UUID,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AskConversationOut:
    await doc_service.get_document(db, document_id, owner_id=_user.id)
    conversation = await ask_conv_service.load_conversation_with_messages(
        db,
        owner_id=_user.id,
        document_id=document_id,
    )
    if conversation is None:
        return AskConversationOut(id=None, document_id=document_id, messages=[])

    messages = ask_conv_service.sort_messages_chronologically(list(conversation.messages))
    return AskConversationOut(
        id=conversation.id,
        document_id=document_id,
        updated_at=conversation.updated_at,
        messages=[_ask_message_out(m) for m in messages],
    )


@router.post(
    "/api/documents/{document_id}/ask/conversation/new",
    response_model=AskConversationOut,
)
async def new_ask_conversation(
    document_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AskConversationOut:
    await doc_service.get_document(db, document_id, owner_id=_user.id)
    conversation = await ask_conv_service.replace_with_new_conversation(
        db,
        owner_id=_user.id,
        document_id=document_id,
    )
    return AskConversationOut(
        id=conversation.id,
        document_id=document_id,
        updated_at=conversation.updated_at,
        messages=[],
    )


@router.delete(
    "/api/documents/{document_id}/ask/conversation",
    response_model=MessageOut,
)
async def clear_ask_conversation(
    document_id: uuid.UUID,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    await doc_service.get_document(db, document_id, owner_id=_user.id)
    deleted = await ask_conv_service.clear_conversation(
        db,
        owner_id=_user.id,
        document_id=document_id,
    )
    if deleted:
        return MessageOut(message="Conversation cleared")
    return MessageOut(message="No conversation to clear")


def _ask_message_out(message) -> AskMessageOut:
    snapshots: list[AskCitationSnapshotOut] = []
    raw = message.citations or []
    for item in raw:
        if not isinstance(item, dict):
            continue
        try:
            snapshots.append(
                AskCitationSnapshotOut(
                    display_number=int(item["display_number"]),
                    chunk_id=uuid.UUID(str(item["chunk_id"])),
                    document_id=uuid.UUID(str(item["document_id"])),
                    page_number=item.get("page_number"),
                    title=item.get("title"),
                    quote=item.get("quote"),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return AskMessageOut(
        id=message.id,
        role=message.role,
        content=message.content,
        citations=snapshots,
        created_at=message.created_at,
    )


@router.post("/api/documents/{document_id}/ask", response_model=AskResponse)
async def ask_document(
    document_id: uuid.UUID,
    body: AskRequest,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AskResponse:
    await doc_service.get_document(db, document_id, owner_id=_user.id)
    (
        settings_row,
        chat_provider,
        chat_model,
        chat_adapter,
        embed_adapter,
        embed_model,
        embed_provider_name,
    ) = await _resolve_ai_for_ask(db, body.confirm_remote)

    conversation = await ask_conv_service.get_or_create_conversation(
        db,
        owner_id=_user.id,
        document_id=document_id,
    )
    prior = await ask_conv_service.list_messages(db, conversation_id=conversation.id)
    profile = resolve_profile(settings_row)
    history = ask_conv_service.select_history_for_model(
        prior,
        token_budget=profile.conversation_history_tokens,
    )

    scope = RAGScope(kind="document", document_id=document_id)
    result = await rag_ask(
        db,
        owner_id=_user.id,
        question=body.question,
        settings=settings_row,
        chat_provider=chat_provider,
        chat_adapter=chat_adapter,
        chat_model=chat_model,
        scope=scope,
        embed_adapter=embed_adapter,
        embedding_model=embed_model,
        embedding_provider=embed_provider_name,
        conversation=history or None,
    )

    display_answer, citation_snapshots = ask_conv_service.rewrite_answer_with_display_citations(
        result.answer,
        result.citations,
    )
    if result.insufficient_evidence:
        display_answer = (
            "I couldn't find enough evidence in this document to answer that reliably.\n\n"
            "Try asking about a specific chapter, concept, or passage."
        )
        citation_snapshots = []

    persist_failed = False
    user_message_id = None
    assistant_message_id = None
    try:
        from datetime import timedelta

        user_msg = await ask_conv_service.append_message(
            db,
            conversation_id=conversation.id,
            role=ask_conv_service.ROLE_USER,
            content=body.question.strip(),
        )
        assistant_msg = await ask_conv_service.append_message(
            db,
            conversation_id=conversation.id,
            role=ask_conv_service.ROLE_ASSISTANT,
            content=display_answer,
            citations=citation_snapshots or None,
            # Guarantee assistant sorts after its user turn even if clocks collide.
            created_at=user_msg.created_at + timedelta(milliseconds=1),
        )
        user_message_id = user_msg.id
        assistant_message_id = assistant_msg.id
    except Exception:
        import logging

        logging.getLogger(__name__).exception(
            "ask conversation persist failed for document=%s",
            document_id,
        )
        persist_failed = True

    numbered_citations = [
        CitationOut(
            document_id=uuid.UUID(snap["document_id"]),
            page_number=snap.get("page_number"),
            chunk_id=uuid.UUID(snap["chunk_id"]),
            title=snap.get("title") or "",
            quote=snap.get("quote"),
            display_number=int(snap["display_number"]),
        )
        for snap in citation_snapshots
    ]

    return AskResponse(
        answer=display_answer,
        citations=numbered_citations,
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
        conversation_id=conversation.id,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        persist_failed=persist_failed,
    )


@router.post("/api/documents/bulk", response_model=MessageOut)
async def bulk_action(
    body: BulkActionRequest,
    _sess: SafeSession,
    _user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> MessageOut:
    count = 0
    for doc_id in body.document_ids:
        if body.action == "trash":
            await doc_service.trash_document(db, doc_id, owner_id=_user.id)
        elif body.action == "restore":
            await doc_service.restore_document(db, doc_id, owner_id=_user.id)
        elif body.action == "move":
            if body.folder_id is None:
                raise ValidationError("folder_id is required for move action")
            await doc_service.move_document(db, doc_id, body.folder_id, owner_id=_user.id)
        elif body.action in {"archive", "unarchive"}:
            doc = await doc_service.get_document(db, doc_id, owner_id=_user.id)
            doc.is_archived = body.action == "archive"
            await db.flush()
        elif body.action in {"tag", "untag"}:
            if not body.tag_ids:
                raise ValidationError("tag_ids is required for tag/untag actions")
            doc = await doc_service.get_document(db, doc_id, owner_id=_user.id)
            tag_rows = (
                (
                    await db.execute(
                        select(Tag).where(
                            Tag.owner_id == _user.id,
                            Tag.id.in_(body.tag_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
            if len(tag_rows) != len(set(body.tag_ids)):
                raise NotFoundError("One or more tags not found")
            if body.action == "tag":
                existing = {t.id for t in doc.tags}
                doc.tags = list(doc.tags) + [t for t in tag_rows if t.id not in existing]
            else:
                remove = {t.id for t in tag_rows}
                doc.tags = [t for t in doc.tags if t.id not in remove]
            await db.flush()
        else:
            raise ValidationError(f"Unknown bulk action: {body.action}")
        count += 1
    return MessageOut(message=f"Applied {body.action} to {count} document(s)")
