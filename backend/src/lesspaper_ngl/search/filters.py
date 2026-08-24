"""Shared document filter application for search and FTS."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, or_
from sqlalchemy.orm import Query

from lesspaper_ngl.models import Document, ProcessingStatus, Tag


@dataclass(frozen=True)
class DocumentSearchFilters:
    owner_id: uuid.UUID
    folder_id: uuid.UUID | None = None
    folder_ids: list[uuid.UUID] | None = None
    include_trashed: bool = False
    inbox: bool | None = None
    tag_ids: list[uuid.UUID] | None = None
    document_type_id: uuid.UUID | None = None
    correspondent_id: uuid.UUID | None = None
    mime_type: str | None = None
    is_archived: bool | None = None
    date_from: date | None = None
    date_to: date | None = None
    document_indexed: bool | None = None
    has_embeddings: bool | None = None
    unprocessed: bool | None = None


def apply_document_search_filters(stmt: Select | Query, filters: DocumentSearchFilters):
    """Apply owner/trash/folder/metadata/readiness filters to a Document-joined stmt."""
    stmt = stmt.where(Document.owner_id == filters.owner_id)
    if not filters.include_trashed:
        stmt = stmt.where(Document.is_trashed.is_(False))
    if filters.folder_id is not None:
        stmt = stmt.where(Document.folder_id == filters.folder_id)
    if filters.folder_ids:
        stmt = stmt.where(Document.folder_id.in_(filters.folder_ids))
    if filters.inbox is True:
        stmt = stmt.where(Document.inbox.is_(True))
    elif filters.inbox is False:
        stmt = stmt.where(Document.inbox.is_(False))
    if filters.tag_ids:
        for tag_id in filters.tag_ids:
            stmt = stmt.where(Document.tags.any(Tag.id == tag_id))
    if filters.document_type_id is not None:
        stmt = stmt.where(Document.document_type_id == filters.document_type_id)
    if filters.correspondent_id is not None:
        stmt = stmt.where(Document.correspondent_id == filters.correspondent_id)
    if filters.mime_type:
        stmt = stmt.where(Document.mime_type == filters.mime_type)
    if filters.is_archived is True:
        stmt = stmt.where(Document.is_archived.is_(True))
    elif filters.is_archived is False:
        stmt = stmt.where(Document.is_archived.is_(False))
    if filters.date_from is not None:
        stmt = stmt.where(Document.added_date >= filters.date_from)
    if filters.date_to is not None:
        stmt = stmt.where(Document.added_date <= filters.date_to)
    if filters.document_indexed is True:
        stmt = stmt.where(Document.document_indexed.is_(True))
    elif filters.document_indexed is False:
        stmt = stmt.where(Document.document_indexed.is_(False))
    if filters.has_embeddings is True:
        stmt = stmt.where(Document.has_embeddings.is_(True))
    elif filters.has_embeddings is False:
        stmt = stmt.where(Document.has_embeddings.is_(False))
    if filters.unprocessed is True:
        stmt = stmt.where(
            or_(
                Document.inbox.is_(True),
                Document.needs_review.is_(True),
                Document.document_indexed.is_(False),
                Document.processing_status.in_(
                    [
                        ProcessingStatus.PENDING,
                        ProcessingStatus.PROCESSING,
                        ProcessingStatus.FAILED,
                        ProcessingStatus.PARTIAL,
                    ]
                ),
            )
        )
    return stmt
