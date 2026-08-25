"""Streamable HTTP MCP server mounted at /mcp."""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Any, Literal
from urllib.parse import urlparse

from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import select
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from lesspaper_ngl.api.schemas import SearchRequest
from lesspaper_ngl.api.search import execute_search
from lesspaper_ngl.auth import api_tokens as token_service
from lesspaper_ngl.core.config import get_settings
from lesspaper_ngl.core.exceptions import NotFoundError
from lesspaper_ngl.db.session import session_scope
from lesspaper_ngl.models import DocumentPage, User
from lesspaper_ngl.services import documents as doc_service
from lesspaper_ngl.services import folders as folder_service

_TEXT_CAP = 100_000
_DEFAULT_LIMIT = 20

mcp_user: ContextVar[User | None] = ContextVar("lesspaper_ngl_mcp_user", default=None)

mcp = MCPServer(
    "lesspaper-ngl",
    instructions=(
        "Read-only lesspaper-ngl library: search_evidence, search_documents, "
        "get_document, list_folder. Keyword search works without AI. "
        "Do not ask the AI; reason over returned evidence."
    ),
)


def _current_user() -> User:
    user = mcp_user.get()
    if user is None:
        raise PermissionError("Authentication required")
    return user


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    return max(1, min(int(limit), _DEFAULT_LIMIT))


def _parse_uuid(value: str | None, *, field: str) -> uuid.UUID | None:
    if value is None or value.strip() == "":
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field}") from exc


def _transport_security() -> TransportSecuritySettings:
    settings = get_settings()
    allowed_hosts: list[str] = [
        "localhost",
        "localhost:*",
        "127.0.0.1",
        "127.0.0.1:*",
        "api",
        "api:*",
        "web",
        "web:*",
        "test",
        "test:*",
    ]
    allowed_origins: list[str] = ["http://test", "http://localhost", "http://127.0.0.1"]
    seen_hosts: set[str] = set()
    seen_origins: set[str] = set()
    for origin in settings.frontend_origins:
        if origin not in seen_origins:
            seen_origins.add(origin)
            allowed_origins.append(origin)
        host = urlparse(origin).hostname
        if host and host not in seen_hosts:
            seen_hosts.add(host)
            allowed_hosts.append(host)
            allowed_hosts.append(f"{host}:*")
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )


class McpBearerAuth:
    """Reject /mcp without a valid API token. Cookies are not accepted."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        auth = headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            response = JSONResponse({"error": "Authentication required"}, status_code=401)
            await response(scope, receive, send)
            return
        raw = auth[7:].strip()
        async with session_scope() as db:
            user = await token_service.get_user_by_raw_token(db, raw)
        if user is None:
            response = JSONResponse({"error": "Authentication required"}, status_code=401)
            await response(scope, receive, send)
            return
        token = mcp_user.set(user)
        try:
            await self.app(scope, receive, send)
        finally:
            mcp_user.reset(token)


def _flatten_evidence(response: Any, *, limit: int) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    for hit in response.items:
        doc = hit.document
        matches = hit.matches or []
        if not matches:
            units.append(
                {
                    "document_id": str(doc.id),
                    "title": doc.title,
                    "text": hit.snippet,
                    "score": hit.score,
                    "page": hit.page_number,
                    "chunk_id": str(hit.chunk_id) if hit.chunk_id else None,
                }
            )
        else:
            for match in matches:
                units.append(
                    {
                        "document_id": str(doc.id),
                        "title": doc.title,
                        "text": match.snippet or hit.snippet,
                        "score": match.score,
                        "page": match.page_number,
                        "chunk_id": str(match.chunk_id) if match.chunk_id else None,
                    }
                )
        if len(units) >= limit:
            break
    return units[:limit]


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _document_metadata(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(doc["id"]),
        "title": doc["title"],
        "original_filename": doc["original_filename"],
        "folder_id": str(doc["folder_id"]) if doc.get("folder_id") else None,
        "folder_path": doc.get("folder_path"),
        "tags": doc.get("tags") or [],
        "document_type": doc.get("document_type_name"),
        "correspondent": doc.get("correspondent_name"),
        "created_date": str(doc["created_date"]) if doc.get("created_date") else None,
        "added_date": _iso(doc.get("added_date")),
        "language": doc.get("language"),
        "page_count": doc.get("page_count"),
        "inbox": doc.get("inbox"),
        "text_extracted": doc.get("text_extracted"),
        "document_indexed": doc.get("document_indexed"),
        "ocr_completed": doc.get("ocr_completed"),
        "processing_status": doc.get("processing_status"),
        "has_embeddings": doc.get("has_embeddings"),
    }


def _search_request(
    query: str,
    *,
    mode: str,
    folder_id: uuid.UUID | None,
    tag_ids: list[uuid.UUID] | None,
    document_type_id: uuid.UUID | None,
    correspondent_id: uuid.UUID | None,
    inbox: bool | None,
    limit: int,
) -> SearchRequest:
    return SearchRequest(
        query=query,
        mode=mode,  # type: ignore[arg-type]
        folder_id=folder_id,
        tag_ids=tag_ids,
        document_type_id=document_type_id,
        correspondent_id=correspondent_id,
        inbox=inbox,
        page=1,
        page_size=limit,
    )


@mcp.tool()
async def search_evidence(
    query: str,
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid",
    folder_id: str | None = None,
    inbox: bool | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Search lesspaper-ngl for page/chunk evidence. Keyword works without embeddings."""
    if not query.strip():
        raise ValueError("query must not be empty; use list_folder to browse")
    user = _current_user()
    cap = _clamp_limit(limit)
    body = _search_request(
        query.strip(),
        mode=mode,
        folder_id=_parse_uuid(folder_id, field="folder_id"),
        tag_ids=None,
        document_type_id=None,
        correspondent_id=None,
        inbox=inbox,
        limit=cap,
    )
    async with session_scope() as db:
        result = await execute_search(db, user.id, body)
    return {
        "items": _flatten_evidence(result, limit=cap),
        "effective_mode": result.effective_mode,
        "semantic_available": result.semantic_available,
    }


@mcp.tool()
async def search_documents(
    query: str,
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid",
    folder_id: str | None = None,
    inbox: bool | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Find documents by query and filters. Empty query is not browse — use list_folder."""
    if not query.strip():
        raise ValueError("query must not be empty; use list_folder to browse")
    user = _current_user()
    cap = _clamp_limit(limit)
    body = _search_request(
        query.strip(),
        mode=mode,
        folder_id=_parse_uuid(folder_id, field="folder_id"),
        tag_ids=None,
        document_type_id=None,
        correspondent_id=None,
        inbox=inbox,
        limit=cap,
    )
    async with session_scope() as db:
        result = await execute_search(db, user.id, body)
    items = []
    for hit in result.items:
        meta = _document_metadata(hit.document.model_dump(mode="json"))
        meta["score"] = hit.score
        meta["matches"] = [
            {
                "kind": match.kind,
                "score": match.score,
                "snippet": match.snippet,
                "page": match.page_number,
                "chunk_id": str(match.chunk_id) if match.chunk_id else None,
            }
            for match in hit.matches
        ]
        items.append(meta)
    return {
        "items": items,
        "total": result.document_total,
        "effective_mode": result.effective_mode,
        "semantic_available": result.semantic_available,
    }


@mcp.tool()
async def get_document(document_id: str) -> dict[str, Any]:
    """Return canonical metadata and extracted page text for one owned document."""
    user = _current_user()
    doc_uuid = _parse_uuid(document_id, field="document_id")
    if doc_uuid is None:
        raise ValueError("document_id is required")
    async with session_scope() as db:
        try:
            doc = await doc_service.get_document(db, doc_uuid, owner_id=user.id)
        except NotFoundError:
            raise ValueError("Document not found") from None
        pages = (
            (
                await db.execute(
                    select(DocumentPage)
                    .where(DocumentPage.document_id == doc.id)
                    .order_by(DocumentPage.page_number)
                )
            )
            .scalars()
            .all()
        )
        meta = _document_metadata(doc_service.document_to_dict(doc))
    page_payload: list[dict[str, Any]] = []
    used = 0
    truncated = False
    for page in pages:
        text = page.text or ""
        remaining = _TEXT_CAP - used
        if remaining <= 0:
            truncated = True
            break
        if len(text) > remaining:
            page_payload.append({"page_number": page.page_number, "text": text[:remaining]})
            truncated = True
            break
        page_payload.append({"page_number": page.page_number, "text": text})
        used += len(text)
    text_available = any((page.text or "").strip() for page in pages)
    return {
        "document": meta,
        "pages": page_payload,
        "text_available": text_available,
        "truncated": truncated,
    }


@mcp.tool()
async def list_folder(
    folder_id: str | None = None,
    recursive: bool = False,
) -> dict[str, Any]:
    """Browse logical lesspaper-ngl folders (not filesystem paths)."""
    user = _current_user()
    folder_uuid = _parse_uuid(folder_id, field="folder_id")
    async with session_scope() as db:
        tree = await folder_service.list_folder_tree(db, user.id)
        counts = await folder_service.folder_counts(db, user.id)

        def folder_dict(folder: Any) -> dict[str, Any]:
            children_count, document_count = counts.get(folder.id, (0, 0))
            return {
                "id": str(folder.id),
                "name": folder.name,
                "parent_id": str(folder.parent_id) if folder.parent_id else None,
                "kind": folder.kind.value if hasattr(folder.kind, "value") else str(folder.kind),
                "path": folder.path_cache,
                "children_count": children_count,
                "document_count": document_count,
            }

        if folder_uuid is None:
            return {"folders": [folder_dict(folder) for folder in tree], "documents": []}

        try:
            folder = await folder_service.get_folder(db, folder_uuid, owner_id=user.id)
        except NotFoundError:
            raise ValueError("Folder not found") from None
        if folder.is_trashed:
            raise ValueError("Folder not found")
        children = [f for f in tree if f.parent_id == folder.id]
        docs, total = await doc_service.list_documents(
            db,
            owner_id=user.id,
            folder_id=folder.id,
            include_descendants=recursive,
            trashed=False,
            page=1,
            page_size=_DEFAULT_LIMIT,
        )
        return {
            "folder": folder_dict(folder),
            "folders": [folder_dict(child) for child in children],
            "documents": [_document_metadata(doc_service.document_to_dict(d)) for d in docs],
            "document_total": total,
        }


def build_mcp_asgi() -> ASGIApp:
    http = mcp.streamable_http_app(
        streamable_http_path="/",
        stateless_http=True,
        json_response=True,
        transport_security=_transport_security(),
    )
    return McpBearerAuth(http)
