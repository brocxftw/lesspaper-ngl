"""Shared exceptions."""

from __future__ import annotations


class FoliumError(Exception):
    """Base lesspaper-ngl error."""

    def __init__(self, message: str, *, code: str = "folium_error") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class NotFoundError(FoliumError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, code="not_found")


class ConflictError(FoliumError):
    def __init__(self, message: str, *, code: str = "conflict") -> None:
        super().__init__(message, code=code)


class DuplicateDocumentError(ConflictError):
    def __init__(self, message: str, *, existing_document_id: str) -> None:
        super().__init__(message, code="duplicate_document")
        self.existing_document_id = existing_document_id


class ValidationError(FoliumError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="validation_error")


class StorageUnavailableError(FoliumError):
    def __init__(self, message: str = "Document storage is unavailable") -> None:
        super().__init__(message, code="storage_unavailable")


class PrivacyViolationError(FoliumError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="privacy_violation")


class AuthError(FoliumError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, code="auth_error")


class ForbiddenError(FoliumError):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message, code="forbidden")


class InsufficientEvidenceError(FoliumError):
    def __init__(self, message: str = "Insufficient evidence was found in the selected documents.") -> None:
        super().__init__(message, code="insufficient_evidence")
