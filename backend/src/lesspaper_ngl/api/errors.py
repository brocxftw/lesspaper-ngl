"""FastAPI exception handlers for lesspaper-ngl errors."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from lesspaper_ngl.ai.base import AIProviderError
from lesspaper_ngl.core.exceptions import (
    AuthError,
    ConflictError,
    DuplicateDocumentError,
    FoliumError,
    ForbiddenError,
    InsufficientEvidenceError,
    NotFoundError,
    PrivacyViolationError,
    StorageUnavailableError,
    ValidationError,
)

_STATUS_MAP: dict[type[FoliumError], int] = {
    NotFoundError: 404,
    ConflictError: 409,
    DuplicateDocumentError: 409,
    ValidationError: 422,
    StorageUnavailableError: 503,
    PrivacyViolationError: 403,
    AuthError: 401,
    ForbiddenError: 403,
    InsufficientEvidenceError: 422,
}


def _error_body(exc: FoliumError) -> dict[str, object]:
    body: dict[str, object] = {
        "code": exc.code,
        "message": exc.message,
    }
    if isinstance(exc, DuplicateDocumentError):
        body["existing_document_id"] = exc.existing_document_id
        body["duplicate"] = True
    return body


async def folium_error_handler(_request: Request, exc: FoliumError) -> JSONResponse:
    status = _STATUS_MAP.get(type(exc), 500)
    return JSONResponse(status_code=status, content=_error_body(exc))


async def ai_provider_error_handler(
    _request: Request, exc: AIProviderError
) -> JSONResponse:
    status = 502
    if exc.status_code is not None and 400 <= exc.status_code < 500:
        status = exc.status_code
    return JSONResponse(
        status_code=status,
        content={
            "code": "ai_provider_error",
            "message": exc.message,
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    for error_type in _STATUS_MAP:
        app.add_exception_handler(error_type, folium_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(AIProviderError, ai_provider_error_handler)
