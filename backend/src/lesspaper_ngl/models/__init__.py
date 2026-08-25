"""SQLAlchemy ORM models for lesspaper-ngl."""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lesspaper_ngl.db.session import Base


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(enum.StrEnum):
    TEXT_EXTRACTION = "text_extraction"
    OCR = "ocr"
    THUMBNAIL = "thumbnail"
    INDEXING = "indexing"
    EMBEDDING = "embedding"
    CLASSIFICATION = "classification"
    SUMMARY = "summary"
    METADATA_SUGGESTION = "metadata_suggestion"
    BACKUP = "backup"
    BACKUP_VERIFY = "backup_verify"


class ProcessingStatus(enum.StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    PARTIAL = "partial"


class PrivacyMode(enum.StrEnum):
    LOCAL_ONLY = "local_only"
    PRIVATE_HYBRID = "private_hybrid"
    STANDARD = "standard"


class AIProfileName(enum.StrEnum):
    LIGHTWEIGHT = "lightweight"
    BALANCED = "balanced"
    QUALITY = "quality"
    CUSTOM = "custom"


class ProviderKind(enum.StrEnum):
    OPENAI_COMPATIBLE = "openai_compatible"
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class AIWorkloadRole(enum.StrEnum):
    INDEXING = "indexing"
    EMBEDDING = "embedding"
    CHAT = "chat"
    VISION = "vision"


class SuggestionStatus(enum.StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class ChunkEmbeddingStatus(enum.StrEnum):
    PENDING = "pending"
    EMBEDDING = "embedding"
    EMBEDDED = "embedded"
    FAILED = "failed"


class FolderKind(enum.StrEnum):
    ROOT = "root"
    INBOX = "inbox"
    TRASH = "trash"
    NORMAL = "normal"


class PasswordResetStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    USED = "used"
    EXPIRED = "expired"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    storage_quota_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ai_monthly_request_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avatar_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    onboarding_version: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    sessions: Mapped[list[Session]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    api_tokens: Mapped[list[ApiToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    invites_created: Mapped[list[Invite]] = relationship(
        back_populates="created_by",
        foreign_keys="Invite.created_by_id",
    )
    password_reset_requests: Mapped[list[PasswordResetRequest]] = relationship(
        back_populates="user",
        foreign_keys="PasswordResetRequest.user_id",
        cascade="all, delete-orphan",
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user: Mapped[User] = relationship(back_populates="sessions")


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    prefix: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="api_tokens")


class Invite(Base, TimestampMixin):
    __tablename__ = "invites"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    storage_quota_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ai_monthly_request_quota: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_by: Mapped[User] = relationship(
        back_populates="invites_created",
        foreign_keys=[created_by_id],
    )


class PasswordResetRequest(Base, TimestampMixin):
    __tablename__ = "password_reset_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[PasswordResetStatus] = mapped_column(
        Enum(
            PasswordResetStatus,
            name="password_reset_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=PasswordResetStatus.PENDING,
        nullable=False,
    )
    reset_token_hash: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    reset_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(
        back_populates="password_reset_requests",
        foreign_keys=[user_id],
    )
    approved_by: Mapped[User | None] = relationship(foreign_keys=[approved_by_id])


class Folder(Base, TimestampMixin):
    __tablename__ = "folders"
    __table_args__ = (
        UniqueConstraint("owner_id", "parent_id", "name", name="uq_folder_owner_sibling_name"),
        Index("ix_folders_parent_id", "parent_id"),
        Index(
            "uq_folders_owner_system_kind",
            "owner_id",
            "kind",
            unique=True,
            postgresql_where=text("kind != 'normal'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folders.id", ondelete="RESTRICT"), nullable=True
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    kind: Mapped[FolderKind] = mapped_column(
        Enum(FolderKind, name="folder_kind", values_callable=lambda x: [e.value for e in x]),
        default=FolderKind.NORMAL,
        nullable=False,
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    path_cache: Mapped[str] = mapped_column(String(2048), default="", nullable=False)
    is_trashed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parent: Mapped[Folder | None] = relationship(remote_side="Folder.id", back_populates="children")
    children: Mapped[list[Folder]] = relationship(back_populates="parent")
    documents: Mapped[list[Document]] = relationship(
        back_populates="folder",
        foreign_keys="Document.folder_id",
    )


class Tag(Base, TimestampMixin):
    __tablename__ = "tags"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_tags_owner_name"),
        UniqueConstraint("owner_id", "slug", name="uq_tags_owner_slug"),
        Index("ix_tags_owner_id", "owner_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[str] = mapped_column(String(16), default="#64748b", nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)

    documents: Mapped[list[Document]] = relationship(
        secondary="document_tags", back_populates="tags"
    )


class DocumentType(Base, TimestampMixin):
    __tablename__ = "document_types"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_document_types_owner_name"),
        UniqueConstraint("owner_id", "slug", name="uq_document_types_owner_slug"),
        Index("ix_document_types_owner_id", "owner_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(128), nullable=False)

    documents: Mapped[list[Document]] = relationship(back_populates="document_type")


class Correspondent(Base, TimestampMixin):
    __tablename__ = "correspondents"
    __table_args__ = (
        UniqueConstraint("owner_id", "name", name="uq_correspondents_owner_name"),
        UniqueConstraint("owner_id", "slug", name="uq_correspondents_owner_slug"),
        Index("ix_correspondents_owner_id", "owner_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), nullable=False)

    documents: Mapped[list[Document]] = relationship(back_populates="correspondent")


class Document(Base, TimestampMixin):
    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_folder_id", "folder_id"),
        Index("ix_documents_owner_id", "owner_id"),
        Index("ix_documents_checksum", "checksum"),
        Index("ix_documents_storage_key", "storage_key"),
        Index("ix_documents_title", "title"),
        Index("ix_documents_search_vector", "search_vector", postgresql_using="gin"),
        Index("uq_documents_owner_checksum", "owner_id", "checksum", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    language: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    archive_serial: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    folder_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("folders.id", ondelete="RESTRICT"), nullable=False
    )
    document_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_types.id", ondelete="SET NULL"), nullable=True
    )
    correspondent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("correspondents.id", ondelete="SET NULL"), nullable=True
    )

    created_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    added_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    modified_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(
            ProcessingStatus,
            name="processing_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ProcessingStatus.PENDING,
        nullable=False,
    )
    ocr_completed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    ocr_pages_done: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ocr_pages_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text_extracted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    document_indexed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_embeddings: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    chunks_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunks_embedded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    chunks_failed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    embedding_finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_trashed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    trashed_from_folder_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("folders.id", ondelete="SET NULL"),
        nullable=True,
    )
    inbox: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    custom_fields: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_summary_meta: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR, nullable=True)
    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    thumbnail_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    preview_key: Mapped[str | None] = mapped_column(String(512), nullable=True)

    folder: Mapped[Folder] = relationship(
        back_populates="documents",
        foreign_keys=[folder_id],
    )
    document_type: Mapped[DocumentType | None] = relationship(back_populates="documents")
    correspondent: Mapped[Correspondent | None] = relationship(back_populates="documents")
    tags: Mapped[list[Tag]] = relationship(secondary="document_tags", back_populates="documents")
    pages: Mapped[list[DocumentPage]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentPage.page_number"
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    suggestions: Mapped[list[AISuggestion]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentTag(Base):
    __tablename__ = "document_tags"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    tag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"
    __table_args__ = (
        UniqueConstraint("document_id", "page_number", name="uq_document_page"),
        Index(
            "ix_document_pages_search_vector",
            "search_vector",
            postgresql_using="gin",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR, nullable=True)

    document: Mapped[Document] = relationship(back_populates="pages")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_document_id", "document_id"),
        Index("ix_document_chunks_embedding_space", "embedding_provider", "embedding_model"),
        Index("ix_document_chunks_document_status", "document_id", "embedding_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(512), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunking_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    embedding_status: Mapped[ChunkEmbeddingStatus] = mapped_column(
        Enum(
            ChunkEmbeddingStatus,
            name="chunk_embedding_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=ChunkEmbeddingStatus.PENDING,
        nullable=False,
    )
    embedding_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Store up to 3072 dims; actual query filters by dimension/model
    embedding: Mapped[Any | None] = mapped_column(Vector(3072), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    document: Mapped[Document] = relationship(back_populates="chunks")


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_status_priority", "status", "priority", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    job_type: Mapped[JobType] = mapped_column(
        Enum(JobType, name="job_type", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", values_callable=lambda x: [e.value for e in x]),
        default=JobStatus.QUEUED,
        nullable=False,
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    available_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIProvider(Base, TimestampMixin):
    __tablename__ = "ai_providers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    kind: Mapped[ProviderKind] = mapped_column(
        Enum(ProviderKind, name="provider_kind", values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    encrypted_api_key: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_local: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    chat_model: Mapped[str | None] = mapped_column(String(256), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String(256), nullable=True)
    vision_model: Mapped[str | None] = mapped_column(String(256), nullable=True)

    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_structured_output: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    supports_embeddings: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Embedding pipeline capabilities (nullable → code defaults)
    embedding_max_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_recommended_chunk_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_batch_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_max_batch_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding_concurrency: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Optional provider privacy preferences (not lesspaper-ngl-enforced guarantees)
    no_training: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    zero_retention: Mapped[bool] = mapped_column(Boolean, default=False, nullable=True)
    extra: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    last_probe_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_probe_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_probe_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_probe_model_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_probed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIModelAssignment(Base, TimestampMixin):
    __tablename__ = "ai_model_assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    role: Mapped[AIWorkloadRole] = mapped_column(
        Enum(
            AIWorkloadRole,
            name="ai_workload_role",
            values_callable=lambda x: [e.value for e in x],
        ),
        unique=True,
        nullable=False,
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_providers.id", ondelete="SET NULL"), nullable=True
    )
    model: Mapped[str | None] = mapped_column(String(256), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    provider: Mapped[AIProvider | None] = relationship()


class AISettings(Base, TimestampMixin):
    """Singleton-ish app AI settings row (id=1)."""

    __tablename__ = "ai_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    privacy_mode: Mapped[PrivacyMode] = mapped_column(
        Enum(PrivacyMode, name="privacy_mode", values_callable=lambda x: [e.value for e in x]),
        default=PrivacyMode.LOCAL_ONLY,
        nullable=False,
    )
    profile: Mapped[AIProfileName] = mapped_column(
        Enum(AIProfileName, name="ai_profile_name", values_callable=lambda x: [e.value for e in x]),
        default=AIProfileName.LIGHTWEIGHT,
        nullable=False,
    )
    chat_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_providers.id", ondelete="SET NULL"), nullable=True
    )
    embedding_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_providers.id", ondelete="SET NULL"), nullable=True
    )
    vision_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ai_providers.id", ondelete="SET NULL"), nullable=True
    )
    allow_remote_embeddings: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_remote_qa: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_remote_vision: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    warn_before_remote: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    block_remote_ai: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_enrichment: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_tagging: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Custom profile overrides
    retrieved_chunks: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    max_context_tokens: Mapped[int] = mapped_column(Integer, default=8000, nullable=False)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=2048, nullable=False)
    conversation_history_tokens: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    parallel_llm_calls: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Cosine similarity floor for semantic Ask hits; NULL disables filtering.
    semantic_min_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    active_embedding_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active_embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    active_embedding_dimension: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AIUsage(Base):
    __tablename__ = "ai_usage"
    __table_args__ = (
        Index("ix_ai_usage_created_at", "created_at"),
        Index("ix_ai_usage_user_id", "user_id"),
        Index("ix_ai_usage_created_operation", "created_at", "operation"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reported_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cost_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    is_local: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AISuggestion(Base, TimestampMixin):
    __tablename__ = "ai_suggestions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[SuggestionStatus] = mapped_column(
        Enum(
            SuggestionStatus,
            name="suggestion_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=SuggestionStatus.PENDING,
        nullable=False,
    )
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    document: Mapped[Document] = relationship(back_populates="suggestions")


class AskConversation(Base, TimestampMixin):
    """One active Ask lesspaper-ngl conversation per owner+document (V1)."""

    __tablename__ = "ask_conversations"
    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "document_id",
            name="uq_ask_conversations_owner_document",
        ),
        Index("ix_ask_conversations_owner_id", "owner_id"),
        Index("ix_ask_conversations_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )

    messages: Mapped[list[AskMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AskMessage.created_at",
    )


class AskMessage(Base):
    __tablename__ = "ask_messages"
    __table_args__ = (
        Index("ix_ask_messages_conversation_id", "conversation_id"),
        Index("ix_ask_messages_created_at", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ask_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Validated citation snapshots for assistant messages (display_number, chunk_id, …).
    citations: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    conversation: Mapped[AskConversation] = relationship(back_populates="messages")


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class BackupScheduleType(enum.StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    INTERVAL_HOURS = "interval_hours"


class BackupRecordStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BackupVerificationStatus(enum.StrEnum):
    HEALTHY = "healthy"
    UNVERIFIED = "unverified"
    CORRUPTED = "corrupted"
    INCOMPATIBLE = "incompatible"
    FAILED = "failed"


class InstanceState(enum.StrEnum):
    UNINITIALISED = "uninitialised"
    INITIALISING = "initialising"
    READY = "ready"
    RESTORING = "restoring"
    RECOVERING = "recovering"
    FAILED = "failed"


class BackupSettings(Base, TimestampMixin):
    """Singleton backup policy (id=1)."""

    __tablename__ = "backup_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    schedule_type: Mapped[BackupScheduleType] = mapped_column(
        Enum(BackupScheduleType, name="backup_schedule_type", values_callable=lambda x: [e.value for e in x]),
        default=BackupScheduleType.DAILY,
        nullable=False,
    )
    backup_time: Mapped[str] = mapped_column(String(5), default="02:00", nullable=False)
    weekday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repository_subdir: Mapped[str] = mapped_column(String(256), default="", nullable=False)
    retention_count: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    verify_after_backup: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BackupRecord(Base, TimestampMixin):
    __tablename__ = "backup_records"
    __table_args__ = (Index("ix_backup_records_created_at", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    relative_key: Mapped[str] = mapped_column(String(512), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    document_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    folium_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    schema_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    format_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[BackupRecordStatus] = mapped_column(
        Enum(BackupRecordStatus, name="backup_record_status", values_callable=lambda x: [e.value for e in x]),
        default=BackupRecordStatus.QUEUED,
        nullable=False,
    )
    verification_status: Mapped[BackupVerificationStatus] = mapped_column(
        Enum(
            BackupVerificationStatus,
            name="backup_verification_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=BackupVerificationStatus.UNVERIFIED,
        nullable=False,
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    progress_stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
    )


class LibraryActivityCounters(Base, TimestampMixin):
    """Increment-only owner activity counters since last reset."""

    __tablename__ = "library_activity_counters"

    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    documents_ingested: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    bytes_ingested: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    pages_processed: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    successful_processing: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    ocr_pages: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    failed_documents: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    duplicates_rejected: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    purged_documents: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    reset_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ApplicationLog(Base):
    __tablename__ = "application_logs"
    __table_args__ = (
        Index("ix_application_logs_timestamp", "timestamp"),
        Index("ix_application_logs_level_service", "level", "service"),
        Index("ix_application_logs_request_id", "request_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    level: Mapped[str] = mapped_column(String(16), nullable=False)
    service: Mapped[str] = mapped_column(String(32), nullable=False)
    module: Mapped[str] = mapped_column(String(256), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
