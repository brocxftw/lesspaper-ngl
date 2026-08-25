"""Pydantic API schemas."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---- Auth ----


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32)
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=128)
    invite_token: str | None = None


class ProfileUpdateRequest(BaseModel):
    username: str | None = Field(default=None, min_length=3, max_length=32)
    display_name: str | None = Field(default=None, min_length=1, max_length=128)


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8, max_length=128)


class UserOut(ORMModel):
    id: UUID
    username: str
    display_name: str
    is_admin: bool
    is_active: bool = True
    storage_quota_bytes: int | None = None
    ai_monthly_request_quota: int | None = None
    has_avatar: bool = False


class UserUsageOut(BaseModel):
    storage_used_bytes: int
    storage_quota_bytes: int | None
    ai_requests_this_month: int
    ai_monthly_request_quota: int | None


class UserAdminOut(UserOut):
    created_at: datetime
    storage_used_bytes: int = 0
    ai_requests_this_month: int = 0


class UserAdminUpdate(BaseModel):
    is_admin: bool | None = None
    is_active: bool | None = None
    storage_quota_bytes: int | None = None
    ai_monthly_request_quota: int | None = None
    clear_storage_quota: bool = False
    clear_ai_quota: bool = False


class AdminSetPasswordRequest(BaseModel):
    password: str = Field(min_length=8, max_length=128)


class ForgotPasswordRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)


class ForgotPasswordOut(BaseModel):
    message: str


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)


class ResetPasswordValidateOut(BaseModel):
    valid: bool
    username: str | None = None


class PasswordResetRequestOut(ORMModel):
    id: UUID
    user_id: UUID
    username: str
    display_name: str
    status: str
    created_at: datetime
    approved_at: datetime | None = None
    reset_url_token: str | None = None  # only on approve


class InviteCreateRequest(BaseModel):
    expires_in_hours: int = Field(default=168, ge=1, le=720)
    storage_quota_bytes: int | None = None
    ai_monthly_request_quota: int | None = None


class InviteOut(ORMModel):
    id: UUID
    expires_at: datetime
    used_at: datetime | None
    storage_quota_bytes: int | None
    ai_monthly_request_quota: int | None
    created_at: datetime
    invite_url_token: str | None = None  # only on create


class RegistrationStatusOut(BaseModel):
    allow_registration: bool


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str


class ApiTokenCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class ApiTokenOut(ORMModel):
    id: UUID
    name: str
    prefix: str
    created_at: datetime
    last_used_at: datetime | None = None


class ApiTokenCreatedOut(ApiTokenOut):
    token: str


class UserSessionOut(ORMModel):
    id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    user_agent: str | None
    ip_address: str | None
    current: bool = False


# ---- Folders ----


class FolderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    parent_id: UUID | None = None


class FolderUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    parent_id: UUID | None = None
    sort_order: int | None = None


class FolderOut(ORMModel):
    id: UUID
    name: str
    parent_id: UUID | None
    kind: str
    sort_order: int
    path_cache: str
    is_trashed: bool = False
    trashed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    children_count: int = 0
    document_count: int = 0
    purge_after: datetime | None = None


class FolderDeleteRequest(BaseModel):
    strategy: Literal["move_to_parent", "move_to_inbox", "delete_documents", "trash"] = "trash"
    confirm_destructive: bool = False


class TrashPurgeOut(BaseModel):
    deleted_documents: int
    deleted_folders: int
    retention_days: int


# ---- Tags / types / correspondents ----


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    color: str = Field(default="#64748b", max_length=16)


class TagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    color: str | None = None


class TagOut(ORMModel):
    id: UUID
    name: str
    color: str
    slug: str
    document_count: int = 0


class TagMerge(BaseModel):
    source_tag_id: UUID
    target_tag_id: UUID


class NamedEntityCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class NamedEntityOut(ORMModel):
    id: UUID
    name: str
    slug: str


# ---- Documents ----


class DocumentMetadataUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=512)
    folder_id: UUID | None = None
    document_type_id: UUID | None = None
    correspondent_id: UUID | None = None
    tag_ids: list[UUID] | None = None
    created_date: date | None = None
    effective_date: date | None = None
    language: str | None = None
    notes: str | None = None
    custom_fields: dict[str, Any] | None = None
    pending_folder_path: str | None = None
    inbox: bool | None = None
    is_archived: bool | None = None
    needs_review: bool | None = None


class DocumentProcessRequest(BaseModel):
    document_ids: list[UUID] = Field(min_length=1, max_length=200)


class DocumentProcessResultOut(BaseModel):
    processed: list[dict[str, Any]]
    skipped: list[dict[str, Any]]
    failed: list[dict[str, Any]]


class DocumentRemoveQueueRequest(BaseModel):
    document_ids: list[UUID] = Field(min_length=1, max_length=200)


class DocumentMoveRequest(BaseModel):
    folder_id: UUID


class TagOutBrief(ORMModel):
    id: UUID
    name: str
    color: str


class DocumentOut(ORMModel):
    id: UUID
    title: str
    original_filename: str
    mime_type: str
    file_size: int
    page_count: int | None
    language: str | None
    notes: str | None
    archive_serial: str | None
    folder_id: UUID
    folder_path: str | None = None
    document_type_id: UUID | None
    document_type_name: str | None = None
    correspondent_id: UUID | None
    correspondent_name: str | None = None
    tags: list[TagOutBrief] = []
    created_date: date | None
    effective_date: date | None
    added_date: datetime
    modified_date: datetime
    indexed_at: datetime | None
    processing_status: str
    ocr_completed: bool
    ocr_pages_done: int | None = None
    ocr_pages_total: int | None = None
    text_extracted: bool
    document_indexed: bool
    has_embeddings: bool
    chunks_total: int | None = None
    chunks_embedded: int | None = None
    chunks_failed: int | None = None
    embedding_error: str | None = None
    embedding_started_at: datetime | None = None
    embedding_finished_at: datetime | None = None
    processing_error: str | None
    is_archived: bool
    is_trashed: bool
    trashed_at: datetime | None
    trashed_from_folder_id: UUID | None = None
    purge_after: datetime | None = None
    inbox: bool
    needs_review: bool
    inbox_status: Literal["preparing", "ready", "needs_review", "failed"] | None = None
    pending_folder_path: str | None = None
    custom_fields: dict[str, Any]
    ai_summary: str | None
    ai_summary_meta: dict[str, Any] | None
    has_thumbnail: bool = False
    created_at: datetime
    updated_at: datetime


class DocumentListOut(BaseModel):
    items: list[DocumentOut]
    total: int
    page: int
    page_size: int


class InboxOverviewOut(BaseModel):
    range_days: int
    processed: int
    failed: int
    processing: int
    total_ingested: int
    success_rate: float | None = None


class InboxActivityItemOut(DocumentOut):
    activity_status: Literal[
        "queued", "processing", "processed", "needs_review", "failed"
    ]


class InboxActivityListOut(BaseModel):
    items: list[InboxActivityItemOut]
    total: int
    page: int
    page_size: int
    range_days: int
    tab: Literal["recent", "processed", "failed"]


class DocumentPageContentOut(BaseModel):
    page_number: int
    text: str


class DocumentContentOut(BaseModel):
    document_id: UUID
    title: str
    page_count: int
    pages: list[DocumentPageContentOut]


class DuplicateOut(BaseModel):
    duplicate: bool = True
    existing_document_id: UUID
    message: str
    status: Literal["duplicate"] = "duplicate"
    relative_path: str | None = None


class UploadResultOut(BaseModel):
    """Returned when an upload is skipped as a content duplicate."""

    status: Literal["duplicate"]
    duplicate: bool = True
    existing_document_id: UUID
    message: str
    relative_path: str | None = None


class BulkActionRequest(BaseModel):
    document_ids: list[UUID]
    action: Literal["tag", "untag", "move", "trash", "restore", "archive", "unarchive"]
    tag_ids: list[UUID] | None = None
    folder_id: UUID | None = None


# ---- Search ----


class SearchRequest(BaseModel):
    query: str = ""
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"
    folder_id: UUID | None = None
    include_descendants: bool = True
    folder_ids: list[UUID] | None = None
    tag_ids: list[UUID] | None = None
    document_type_id: UUID | None = None
    correspondent_id: UUID | None = None
    mime_type: str | None = None
    is_archived: bool | None = None
    inbox: bool | None = None
    date_from: date | None = None
    date_to: date | None = None
    document_indexed: bool | None = None
    has_embeddings: bool | None = None
    unprocessed: bool | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class SearchScopeSnapshot(BaseModel):
    """Frozen evidence-search scope for Ask/RAG (mode + filters preserved)."""

    query: str = Field(min_length=1, max_length=2000)
    mode: Literal["keyword", "semantic", "hybrid"] = "hybrid"
    folder_id: UUID | None = None
    include_descendants: bool = True
    folder_ids: list[UUID] | None = None
    tag_ids: list[UUID] | None = None
    document_type_id: UUID | None = None
    correspondent_id: UUID | None = None
    mime_type: str | None = None
    is_archived: bool | None = None
    inbox: bool | None = None
    date_from: date | None = None
    date_to: date | None = None
    document_indexed: bool | None = None
    has_embeddings: bool | None = None
    unprocessed: bool | None = None


class SearchMatch(BaseModel):
    kind: Literal["document", "page", "chunk"]
    score: float
    snippet: str | None = None
    page_number: int | None = None
    chunk_id: UUID | None = None


class SearchHit(BaseModel):
    document: DocumentOut
    score: float
    snippet: str | None = None
    page_number: int | None = None
    chunk_id: UUID | None = None
    matches: list[SearchMatch] = Field(default_factory=list)


class SemanticCoverage(BaseModel):
    available: bool
    embedded_documents: int = 0
    searchable_documents: int = 0
    partial: bool = False


class SearchResponse(BaseModel):
    items: list[SearchHit]
    total: int
    document_total: int
    match_total: int
    mode: str
    semantic_available: bool
    semantic_coverage: SemanticCoverage | None = None
    effective_mode: str | None = None


# ---- Ask / RAG ----


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    scope: Literal["document", "documents", "folder", "folder_tree", "search", "library"] = (
        "document"
    )
    document_id: UUID | None = None
    document_ids: list[UUID] | None = None
    folder_id: UUID | None = None
    search_query: str | None = None
    search: SearchScopeSnapshot | None = None
    confirm_remote: bool = False


class CitationOut(BaseModel):
    document_id: UUID
    page_number: int | None
    chunk_id: UUID
    title: str
    quote: str | None = None
    display_number: int | None = None


class AskResponse(BaseModel):
    answer: str
    citations: list[CitationOut]
    passages: list[CitationOut]
    provider: str | None
    model: str | None
    privacy_mode: str
    is_local: bool
    insufficient_evidence: bool = False
    # Continuous-chat extras (document Ask persistence).
    conversation_id: UUID | None = None
    user_message_id: UUID | None = None
    assistant_message_id: UUID | None = None
    persist_failed: bool = False


class AskCitationSnapshotOut(BaseModel):
    display_number: int
    chunk_id: UUID
    document_id: UUID
    page_number: int | None = None
    title: str | None = None
    quote: str | None = None


class AskMessageOut(BaseModel):
    id: UUID
    role: Literal["user", "assistant"]
    content: str
    citations: list[AskCitationSnapshotOut] = Field(default_factory=list)
    created_at: datetime


class AskConversationOut(BaseModel):
    id: UUID | None = None
    document_id: UUID
    messages: list[AskMessageOut] = Field(default_factory=list)
    updated_at: datetime | None = None


# ---- Jobs ----


class JobOut(ORMModel):
    id: UUID
    job_type: str
    status: str
    document_id: UUID | None
    priority: int
    retry_count: int
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


# ---- AI ----


class AIProviderCreate(BaseModel):
    name: str
    kind: Literal["openai_compatible", "openai", "openrouter", "ollama", "anthropic", "gemini"]
    base_url: str
    api_key: str | None = None
    is_local: bool = False
    chat_model: str | None = None
    embedding_model: str | None = None
    vision_model: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool = False
    supports_vision: bool = False
    supports_structured_output: bool = False
    supports_embeddings: bool = False
    embedding_max_input_tokens: int | None = None
    embedding_recommended_chunk_tokens: int | None = None
    embedding_batch_size: int | None = None
    embedding_max_batch_size: int | None = None
    embedding_concurrency: int | None = None
    no_training: bool = False
    zero_retention: bool = False


class AIProviderUpdate(BaseModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    clear_api_key: bool = False
    is_local: bool | None = None
    enabled: bool | None = None
    chat_model: str | None = None
    embedding_model: str | None = None
    vision_model: str | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    supports_tools: bool | None = None
    supports_vision: bool | None = None
    supports_structured_output: bool | None = None
    supports_embeddings: bool | None = None
    embedding_max_input_tokens: int | None = None
    embedding_recommended_chunk_tokens: int | None = None
    embedding_batch_size: int | None = None
    embedding_max_batch_size: int | None = None
    embedding_concurrency: int | None = None
    no_training: bool | None = None
    zero_retention: bool | None = None


class AIProviderOut(ORMModel):
    id: UUID
    name: str
    kind: str
    base_url: str
    has_api_key: bool
    api_key_masked: str | None = None
    is_local: bool
    enabled: bool
    chat_model: str | None
    embedding_model: str | None
    vision_model: str | None
    context_window: int | None
    max_output_tokens: int | None
    supports_tools: bool
    supports_vision: bool
    supports_structured_output: bool
    supports_embeddings: bool
    embedding_max_input_tokens: int | None = None
    embedding_recommended_chunk_tokens: int | None = None
    embedding_batch_size: int | None = None
    embedding_max_batch_size: int | None = None
    embedding_concurrency: int | None = None
    no_training: bool
    zero_retention: bool
    last_probe_status: str | None = None
    last_probe_error: str | None = None
    last_probe_latency_ms: int | None = None
    last_probe_model_count: int | None = None
    last_probed_at: datetime | None = None
    last_success_at: datetime | None = None


class AIProviderProbeOut(BaseModel):
    status: Literal["available", "offline"]
    latency_ms: int
    model_count: int | None = None
    tested_at: datetime
    message: str


class AIProviderModelOut(BaseModel):
    id: str
    kind: Literal["embedding", "chat", "other"]


class AIProviderModelsOut(BaseModel):
    models: list[AIProviderModelOut]
    discoverable: bool
    message: str | None = None


class AIAssignmentUpdate(BaseModel):
    role: Literal["indexing", "embedding", "chat", "vision"]
    provider_id: UUID | None = None
    model: str | None = Field(default=None, max_length=256)


class AIAssignmentOut(BaseModel):
    role: Literal["indexing", "embedding", "chat", "vision"]
    provider_id: UUID | None
    provider_name: str | None
    model: str | None
    is_local: bool | None
    enabled: bool
    status: Literal["configured", "unconfigured", "disabled", "offline"]
    embedding_dimension: int | None = None
    legacy_fallback: bool = False


class AICapabilitiesOut(BaseModel):
    chat_available: bool
    embeddings_available: bool
    auto_tagging: bool
    auto_enrichment: bool
    warn_before_remote_chat: bool
    chat_is_local: bool | None
    privacy_mode: str


class AICapabilityHealthOut(BaseModel):
    status: Literal["available", "unavailable", "checking", "not_configured"]
    provider: str | None = None
    model: str | None = None
    latency_ms: int | None = None
    last_checked: datetime | None = None
    error: str | None = None


class AIHealthOut(BaseModel):
    ocr: AICapabilityHealthOut
    indexing: AICapabilityHealthOut
    embedding: AICapabilityHealthOut
    chat: AICapabilityHealthOut
    auto_tagging: bool
    auto_enrichment: bool


class AIPolicyUpdate(BaseModel):
    privacy_mode: Literal["local_only", "private_hybrid", "standard"] | None = None
    profile: Literal["lightweight", "balanced", "quality", "custom"] | None = None
    chat_provider_id: UUID | None = None
    embedding_provider_id: UUID | None = None
    vision_provider_id: UUID | None = None
    allow_remote_embeddings: bool | None = None
    allow_remote_qa: bool | None = None
    allow_remote_vision: bool | None = None
    warn_before_remote: bool | None = None
    block_remote_ai: bool | None = None
    auto_enrichment: bool | None = None
    auto_tagging: bool | None = None
    retrieved_chunks: int | None = None
    max_context_tokens: int | None = None
    max_output_tokens: int | None = None
    conversation_history_tokens: int | None = None
    parallel_llm_calls: int | None = None
    semantic_min_score: float | None = None


class AIPolicyOut(ORMModel):
    privacy_mode: str
    profile: str
    chat_provider_id: UUID | None
    embedding_provider_id: UUID | None
    vision_provider_id: UUID | None
    allow_remote_embeddings: bool
    allow_remote_qa: bool
    allow_remote_vision: bool
    warn_before_remote: bool
    block_remote_ai: bool
    auto_enrichment: bool
    auto_tagging: bool
    retrieved_chunks: int
    max_context_tokens: int
    max_output_tokens: int
    conversation_history_tokens: int
    parallel_llm_calls: int
    semantic_min_score: float | None = None
    active_embedding_provider: str | None
    active_embedding_model: str | None
    active_embedding_dimension: int | None
    enforcement_note: str = (
        "lesspaper-ngl enforces privacy_mode in application code. "
        "Provider retention/no-training flags are provider policies, not lesspaper-ngl guarantees."
    )


class AIUsagePoint(BaseModel):
    bucket: datetime
    requests: int
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None


class AIUsageBreakdown(BaseModel):
    key: str
    label: str
    requests: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    duration_ms: int | None = None


class AIUsageTotals(BaseModel):
    requests: int
    input_tokens: int | None
    output_tokens: int | None
    duration_ms: int | None
    estimated_cost: float | None
    cost_currency: str | None
    cost_coverage: Literal["none", "partial", "complete", "local_only"]


class AIUsageSummary(BaseModel):
    range: Literal["today", "7d", "30d", "month"]
    interval: Literal["hour", "day"]
    timezone: Literal["UTC"] = "UTC"
    starts_at: datetime
    ends_at: datetime
    totals: AIUsageTotals
    time_series: list[AIUsagePoint]
    by_provider: list[AIUsageBreakdown]
    by_workload: list[AIUsageBreakdown]


class SuggestionOut(ORMModel):
    id: UUID
    document_id: UUID
    field: str
    value: dict[str, Any]
    status: str
    provider: str | None
    model: str | None
    confidence: float | None


class HealthOut(BaseModel):
    status: str
    version: str = "0.1.0"
    instance_state: str = "ready"


class BackupRepositoryHealthOut(BaseModel):
    configured: bool
    exists: bool
    readable: bool
    writable: bool
    path: str
    free_bytes: int | None
    message: str


class BackupSettingsOut(BaseModel):
    enabled: bool
    schedule_type: str
    backup_time: str
    weekday: int | None
    interval_hours: int | None
    repository_subdir: str
    retention_count: int
    verify_after_backup: bool
    last_success_at: datetime | None
    next_run_at: datetime | None
    repository: BackupRepositoryHealthOut


class BackupSettingsUpdate(BaseModel):
    enabled: bool | None = None
    schedule_type: str | None = None
    backup_time: str | None = None
    weekday: int | None = None
    interval_hours: int | None = None
    repository_subdir: str | None = None
    retention_count: int | None = Field(default=None, ge=1, le=365)
    verify_after_backup: bool | None = None


class BackupRecordOut(BaseModel):
    id: UUID | None = None
    filename: str
    relative_key: str
    created_at: datetime | None = None
    completed_at: datetime | None = None
    size_bytes: int | None = None
    document_count: int | None = None
    folium_version: str | None = None
    schema_version: str | None = None
    format_version: int | None = None
    status: str
    verification_status: str
    verified_at: datetime | None = None
    error_message: str | None = None
    progress_stage: str | None = None


class BackupInspectOut(BaseModel):
    manifest: dict[str, Any]
    verification_status: str
    compatible: bool
    messages: list[str]


class BackupConfirmIn(BaseModel):
    confirm: bool = False


class BackupRestoreStatusOut(BaseModel):
    active: bool
    stage: str
    filename: str | None
    error: str | None
    started_at: str | None
    completed_at: str | None


class BootstrapStatusOut(BaseModel):
    instance_state: str
    ready: bool


class OnboardingStatusOut(BaseModel):
    required: bool
    current_version: int
    completed_version: int


class BootstrapRestoreIn(BaseModel):
    filename: str
    confirm: bool = False


class BootstrapInspectIn(BaseModel):
    filename: str


class WorkerHealthOut(BaseModel):
    status: str
    version: str = "0.1.0"
    last_seen_at: datetime | None = None
    worker_id: str | None = None


class StorageHealthOut(BaseModel):
    status: str
    documents_ok: bool
    consume_ok: bool
    export_ok: bool
    documents_path: str
    consume_path: str
    export_path: str
    message: str


class SystemSummaryOut(BaseModel):
    version: str
    schema_revision: str
    process_uptime_seconds: int
    deployment_mode: str
    services: dict[str, str]
    database_status: str
    storage_status: str
    worker_status: str
    worker_last_seen_at: datetime | None
    document_count: int
    indexed_document_count: int
    queued_jobs: int
    running_jobs: int
    runtime: dict[str, Any]


class StorageMetricsOut(BaseModel):
    configured_source: str | None
    container_path: str
    disk_total_bytes: int | None
    disk_used_bytes: int | None
    disk_free_bytes: int | None
    folium_bytes: int | None
    categories: dict[str, int | None]
    database_bytes: int | None
    database_categories: dict[str, int | None]
    message: str


class DiagnosticsOut(BaseModel):
    generated_at: datetime
    text: str


class ApplicationLogOut(ORMModel):
    id: UUID
    timestamp: datetime
    level: str
    service: str
    module: str
    message: str
    request_id: str | None
    context: dict[str, Any]
    stack_trace: str | None


class ApplicationLogListOut(BaseModel):
    items: list[ApplicationLogOut]
    total: int
    page: int
    page_size: int
    retention_days: int


class AboutOut(BaseModel):
    product: str = "lesspaper-ngl"
    version: str
    description: str
    build_revision: str | None = None
    build_date: str | None = None
    project_links: dict[str, str]


class LibraryActivityOut(BaseModel):
    documents_ingested: int
    bytes_ingested: int
    pages_processed: int
    successful_processing: int
    ocr_pages: int
    failed_documents: int
    duplicates_rejected: int
    purged_documents: int
    reset_at: datetime
    since_label: str


class LibrarySnapshotOut(BaseModel):
    current_documents: int
    library_size_bytes: int
    folders: int
    tags: int
    archived: int
    unprocessed: int


class LibraryFileTypeOut(BaseModel):
    type: str
    mime_type: str
    documents: int
    size_bytes: int
    percentage: float
    usage_percent: int
    icon_colour: str


class LibraryFileTypesOut(BaseModel):
    items: list[LibraryFileTypeOut]
    total_types: int
    total_documents: int
    total_bytes: int


class LibraryHealthOut(BaseModel):
    needs_processing: int
    failed_documents: int
    missing_text: int
    unused_tags: int
    duplicate_content: int
    empty_folders: int


class LibraryOverviewOut(BaseModel):
    activity: LibraryActivityOut
    snapshot: LibrarySnapshotOut
    file_types: LibraryFileTypesOut
    health: LibraryHealthOut
    tags: list[TagOut]


class MessageOut(BaseModel):
    message: str
