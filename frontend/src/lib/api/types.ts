export type UUID = string;

// ---- Auth ----

export interface User {
  id: UUID;
  username: string;
  display_name: string;
  is_admin: boolean;
  is_active?: boolean;
  storage_quota_bytes?: number | null;
  ai_monthly_request_quota?: number | null;
  has_avatar?: boolean;
}

export interface Session {
  user: User;
  csrf_token: string;
}

export interface UserSession {
  id: UUID;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  user_agent: string | null;
  ip_address: string | null;
  current: boolean;
}

export interface ApiToken {
  id: UUID;
  name: string;
  prefix: string;
  created_at: string;
  last_used_at: string | null;
}

export interface ApiTokenCreated extends ApiToken {
  token: string;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  display_name?: string;
  invite_token?: string;
}

export interface ProfileUpdateRequest {
  username?: string;
  display_name?: string;
}

export interface PasswordChangeRequest {
  current_password: string;
  new_password: string;
}

export interface UserUsage {
  storage_used_bytes: number;
  storage_quota_bytes: number | null;
  ai_requests_this_month: number;
  ai_monthly_request_quota: number | null;
}

export interface UserAdmin extends User {
  created_at: string;
  storage_used_bytes: number;
  ai_requests_this_month: number;
}

export interface Invite {
  id: UUID;
  expires_at: string;
  used_at: string | null;
  storage_quota_bytes: number | null;
  ai_monthly_request_quota: number | null;
  created_at: string;
  invite_url_token?: string | null;
}

export interface PasswordResetRequest {
  id: UUID;
  user_id: UUID;
  username: string;
  display_name: string;
  status: string;
  created_at: string;
  approved_at?: string | null;
  reset_url_token?: string | null;
}

// ---- Folders ----

export interface Folder {
  id: UUID;
  name: string;
  parent_id: UUID | null;
  kind: "root" | "inbox" | "trash" | "normal";
  sort_order: number;
  path_cache: string;
  is_trashed?: boolean;
  trashed_at?: string | null;
  purge_after?: string | null;
  created_at: string;
  updated_at: string;
  children_count: number;
  document_count: number;
}

export interface FolderCreate {
  name: string;
  parent_id?: UUID | null;
}

export interface FolderUpdate {
  name?: string;
  parent_id?: UUID | null;
  sort_order?: number;
}

export type FolderDeleteStrategy =
  | "move_to_parent"
  | "move_to_inbox"
  | "delete_documents"
  | "trash";

export interface FolderDeleteRequest {
  strategy: FolderDeleteStrategy;
  confirm_destructive?: boolean;
}

// ---- Tags / types / correspondents ----

export interface Tag {
  id: UUID;
  name: string;
  color: string;
  slug: string;
  document_count: number;
}

export interface TagBrief {
  id: UUID;
  name: string;
  color: string;
}

export interface TagCreate {
  name: string;
  color?: string;
}

export interface TagUpdate {
  name?: string;
  color?: string;
}

export interface TagMerge {
  source_tag_id: UUID;
  target_tag_id: UUID;
}

export interface LibraryActivity {
  documents_ingested: number;
  bytes_ingested: number;
  pages_processed: number;
  successful_processing: number;
  ocr_pages: number;
  failed_documents: number;
  duplicates_rejected: number;
  purged_documents: number;
  reset_at: string;
  since_label: string;
}

export interface LibrarySnapshot {
  current_documents: number;
  library_size_bytes: number;
  folders: number;
  tags: number;
  archived: number;
  unprocessed: number;
}

export interface LibraryFileType {
  type: string;
  mime_type: string;
  documents: number;
  size_bytes: number;
  percentage: number;
  usage_percent: number;
  icon_colour: string;
}

export interface LibraryFileTypes {
  items: LibraryFileType[];
  total_types: number;
  total_documents: number;
  total_bytes: number;
}

export interface LibraryHealth {
  needs_processing: number;
  failed_documents: number;
  missing_text: number;
  unused_tags: number;
  duplicate_content: number;
  empty_folders: number;
}

export interface LibraryOverview {
  activity: LibraryActivity;
  snapshot: LibrarySnapshot;
  file_types: LibraryFileTypes;
  health: LibraryHealth;
  tags: Tag[];
}

export interface NamedEntity {
  id: UUID;
  name: string;
  slug: string;
}

export interface NamedEntityCreate {
  name: string;
}

// ---- Documents ----

export interface Document {
  id: UUID;
  title: string;
  original_filename: string;
  mime_type: string;
  file_size: number;
  page_count: number | null;
  language: string | null;
  notes: string | null;
  archive_serial: string | null;
  folder_id: UUID;
  folder_path: string | null;
  document_type_id: UUID | null;
  document_type_name: string | null;
  correspondent_id: UUID | null;
  correspondent_name: string | null;
  tags: TagBrief[];
  created_date: string | null;
  effective_date: string | null;
  added_date: string;
  modified_date: string;
  indexed_at: string | null;
  processing_status: "pending" | "processing" | "ready" | "failed" | "partial";
  ocr_completed: boolean;
  ocr_pages_done?: number | null;
  ocr_pages_total?: number | null;
  text_extracted: boolean;
  document_indexed: boolean;
  has_embeddings: boolean;
  chunks_total?: number | null;
  chunks_embedded?: number | null;
  chunks_failed?: number | null;
  embedding_error?: string | null;
  embedding_started_at?: string | null;
  embedding_finished_at?: string | null;
  processing_error: string | null;
  is_archived: boolean;
  is_trashed: boolean;
  trashed_at: string | null;
  trashed_from_folder_id?: UUID | null;
  purge_after?: string | null;
  inbox: boolean;
  needs_review: boolean;
  inbox_status?: InboxStatus | null;
  pending_folder_path?: string | null;
  custom_fields: Record<string, unknown>;
  ai_summary: string | null;
  ai_summary_meta: Record<string, unknown> | null;
  has_thumbnail: boolean;
  created_at: string;
  updated_at: string;
}

export type InboxStatus = "preparing" | "ready" | "needs_review" | "failed";

export interface DocumentList {
  items: Document[];
  total: number;
  page: number;
  page_size: number;
}

export interface DocumentMetadataUpdate {
  title?: string;
  folder_id?: UUID;
  document_type_id?: UUID | null;
  correspondent_id?: UUID | null;
  tag_ids?: UUID[];
  created_date?: string | null;
  effective_date?: string | null;
  language?: string | null;
  notes?: string | null;
  custom_fields?: Record<string, unknown>;
  pending_folder_path?: string | null;
  inbox?: boolean;
  is_archived?: boolean;
  needs_review?: boolean;
}

export interface DocumentMoveRequest {
  folder_id: UUID;
}

export type BulkAction =
  | "tag"
  | "untag"
  | "move"
  | "trash"
  | "restore"
  | "archive"
  | "unarchive";

export interface BulkActionRequest {
  document_ids: UUID[];
  action: BulkAction;
  tag_ids?: UUID[];
  folder_id?: UUID;
}

export interface DocumentListParams {
  folder_id?: UUID;
  include_descendants?: boolean;
  inbox?: boolean;
  inbox_status?: InboxStatus;
  trashed?: boolean;
  /** Documents still in the ingestion → indexing lifecycle (not RAG-ready). */
  unprocessed?: boolean;
  tag_ids?: UUID[];
  q?: string;
  page?: number;
  page_size?: number;
  sort?: "added_date" | "title" | "modified_date" | "created_date";
  order?: "asc" | "desc";
}

export interface DocumentProcessResult {
  processed: Array<{ id: string }>;
  skipped: Array<{ id: string; reason?: string }>;
  failed: Array<{ id: string; reason?: string }>;
}

export type InboxActivityStatus =
  | "queued"
  | "processing"
  | "processed"
  | "needs_review"
  | "failed";

export type InboxActivityTab = "recent" | "processed" | "failed";

export interface InboxOverviewMetrics {
  range_days: number;
  processed: number;
  failed: number;
  processing: number;
  total_ingested: number;
  success_rate: number | null;
}

export interface InboxActivityItem extends Document {
  activity_status: InboxActivityStatus;
}

export interface InboxActivityList {
  items: InboxActivityItem[];
  total: number;
  page: number;
  page_size: number;
  range_days: number;
  tab: InboxActivityTab;
}

export interface InboxActivityParams {
  range_days?: 7 | 30;
  tab?: InboxActivityTab;
  q?: string;
  page?: number;
  page_size?: number;
}

export interface DocumentPageContent {
  page_number: number;
  text: string;
}

export interface DocumentContent {
  document_id: string;
  title: string;
  page_count: number;
  pages: DocumentPageContent[];
}

export interface DuplicateError {
  duplicate: boolean;
  existing_document_id: UUID;
  message: string;
}

export interface UploadResult {
  status: "duplicate";
  duplicate: true;
  existing_document_id: UUID;
  message: string;
  relative_path?: string | null;
}

// ---- Search ----

export type SearchMode = "keyword" | "semantic" | "hybrid";

export interface SearchRequest {
  query?: string;
  mode?: SearchMode;
  folder_id?: UUID;
  include_descendants?: boolean;
  folder_ids?: UUID[];
  tag_ids?: UUID[];
  document_type_id?: UUID;
  correspondent_id?: UUID;
  mime_type?: string;
  is_archived?: boolean;
  inbox?: boolean;
  date_from?: string;
  date_to?: string;
  document_indexed?: boolean;
  has_embeddings?: boolean;
  unprocessed?: boolean;
  page?: number;
  page_size?: number;
}

export interface SearchMatch {
  kind: "document" | "page" | "chunk";
  score: number;
  snippet: string | null;
  page_number: number | null;
  chunk_id: UUID | null;
}

export interface SearchHit {
  document: Document;
  score: number;
  snippet: string | null;
  page_number: number | null;
  chunk_id: UUID | null;
  matches?: SearchMatch[];
}

export interface SemanticCoverage {
  available: boolean;
  embedded_documents: number;
  searchable_documents: number;
  partial: boolean;
}

export interface SearchResponse {
  items: SearchHit[];
  total: number;
  document_total?: number;
  match_total?: number;
  mode: string;
  effective_mode?: string | null;
  semantic_available: boolean;
  semantic_coverage?: SemanticCoverage | null;
}

// ---- Ask / RAG ----

export interface SearchScopeSnapshot {
  query: string;
  mode?: SearchMode;
  folder_id?: UUID;
  include_descendants?: boolean;
  folder_ids?: UUID[];
  tag_ids?: UUID[];
  document_type_id?: UUID;
  correspondent_id?: UUID;
  mime_type?: string;
  is_archived?: boolean;
  inbox?: boolean;
  date_from?: string;
  date_to?: string;
  document_indexed?: boolean;
  has_embeddings?: boolean;
  unprocessed?: boolean;
}

export type AskScope =
  | "document"
  | "documents"
  | "folder"
  | "folder_tree"
  | "search"
  | "library";

export interface AskRequest {
  question: string;
  scope?: AskScope;
  document_id?: UUID;
  document_ids?: UUID[];
  folder_id?: UUID;
  search_query?: string;
  search?: SearchScopeSnapshot;
  confirm_remote?: boolean;
}

export interface Citation {
  document_id: UUID;
  page_number: number | null;
  chunk_id: UUID;
  title: string;
  quote: string | null;
  display_number?: number | null;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  passages: Citation[];
  provider: string | null;
  model: string | null;
  privacy_mode: string;
  is_local: boolean;
  insufficient_evidence: boolean;
  conversation_id?: UUID | null;
  user_message_id?: UUID | null;
  assistant_message_id?: UUID | null;
  persist_failed?: boolean;
}

export interface AskCitationSnapshot {
  display_number: number;
  chunk_id: UUID;
  document_id: UUID;
  page_number: number | null;
  title: string | null;
  quote: string | null;
}

export interface AskMessage {
  id: UUID;
  role: "user" | "assistant";
  content: string;
  citations: AskCitationSnapshot[];
  created_at: string;
}

export interface AskConversation {
  id: UUID | null;
  document_id: UUID;
  messages: AskMessage[];
  updated_at: string | null;
}

// ---- Jobs ----

export interface Job {
  id: UUID;
  job_type: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  document_id: UUID | null;
  priority: number;
  retry_count: number;
  error: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

// ---- AI ----

export type AIProviderKind =
  | "openai_compatible"
  | "openai"
  | "openrouter"
  | "ollama"
  | "anthropic"
  | "gemini";

export interface AIProvider {
  id: UUID;
  name: string;
  kind: AIProviderKind;
  base_url: string;
  has_api_key: boolean;
  api_key_masked: string | null;
  is_local: boolean;
  enabled: boolean;
  chat_model: string | null;
  embedding_model: string | null;
  vision_model: string | null;
  context_window: number | null;
  max_output_tokens: number | null;
  supports_tools: boolean;
  supports_vision: boolean;
  supports_structured_output: boolean;
  supports_embeddings: boolean;
  embedding_max_input_tokens?: number | null;
  embedding_recommended_chunk_tokens?: number | null;
  embedding_batch_size?: number | null;
  embedding_max_batch_size?: number | null;
  embedding_concurrency?: number | null;
  no_training: boolean;
  zero_retention: boolean;
  last_probe_status: string | null;
  last_probe_error: string | null;
  last_probe_latency_ms: number | null;
  last_probe_model_count: number | null;
  last_probed_at: string | null;
  last_success_at: string | null;
}

export interface AIProviderCreate {
  name: string;
  kind: AIProviderKind;
  base_url: string;
  api_key?: string;
  is_local?: boolean;
  chat_model?: string;
  embedding_model?: string;
  vision_model?: string;
  context_window?: number;
  max_output_tokens?: number;
  supports_tools?: boolean;
  supports_vision?: boolean;
  supports_structured_output?: boolean;
  supports_embeddings?: boolean;
  embedding_max_input_tokens?: number | null;
  embedding_recommended_chunk_tokens?: number | null;
  embedding_batch_size?: number | null;
  embedding_max_batch_size?: number | null;
  embedding_concurrency?: number | null;
  no_training?: boolean;
  zero_retention?: boolean;
}

export interface AIProviderUpdate {
  name?: string;
  base_url?: string;
  api_key?: string;
  clear_api_key?: boolean;
  is_local?: boolean;
  enabled?: boolean;
  chat_model?: string;
  embedding_model?: string;
  vision_model?: string;
  context_window?: number;
  max_output_tokens?: number;
  supports_tools?: boolean;
  supports_vision?: boolean;
  supports_structured_output?: boolean;
  supports_embeddings?: boolean;
  embedding_max_input_tokens?: number | null;
  embedding_recommended_chunk_tokens?: number | null;
  embedding_batch_size?: number | null;
  embedding_max_batch_size?: number | null;
  embedding_concurrency?: number | null;
  no_training?: boolean;
  zero_retention?: boolean;
}

export type PrivacyMode = "local_only" | "private_hybrid" | "standard";
export type AIProfile = "lightweight" | "balanced" | "quality" | "custom";

export interface AIPolicy {
  privacy_mode: PrivacyMode;
  profile: AIProfile;
  chat_provider_id: UUID | null;
  embedding_provider_id: UUID | null;
  vision_provider_id: UUID | null;
  allow_remote_embeddings: boolean;
  allow_remote_qa: boolean;
  allow_remote_vision: boolean;
  warn_before_remote: boolean;
  block_remote_ai: boolean;
  auto_enrichment: boolean;
  auto_tagging: boolean;
  retrieved_chunks: number;
  max_context_tokens: number;
  max_output_tokens: number;
  conversation_history_tokens: number;
  parallel_llm_calls: number;
  semantic_min_score: number | null;
  active_embedding_provider: string | null;
  active_embedding_model: string | null;
  active_embedding_dimension: number | null;
  enforcement_note: string;
}

export interface AIPolicyUpdate {
  privacy_mode?: PrivacyMode;
  profile?: AIProfile;
  chat_provider_id?: UUID | null;
  embedding_provider_id?: UUID | null;
  vision_provider_id?: UUID | null;
  allow_remote_embeddings?: boolean;
  allow_remote_qa?: boolean;
  allow_remote_vision?: boolean;
  warn_before_remote?: boolean;
  block_remote_ai?: boolean;
  auto_enrichment?: boolean;
  auto_tagging?: boolean;
  retrieved_chunks?: number;
  max_context_tokens?: number;
  max_output_tokens?: number;
  conversation_history_tokens?: number;
  parallel_llm_calls?: number;
  semantic_min_score?: number | null;
}

export type AIWorkloadRole = "indexing" | "embedding" | "chat" | "vision";

export type AIDiscoveredModelKind = "embedding" | "chat" | "other";

export interface AIDiscoveredModel {
  id: string;
  kind: AIDiscoveredModelKind;
}

export interface AIProviderModels {
  models: AIDiscoveredModel[];
  discoverable: boolean;
  message: string | null;
}

export interface AIAssignment {
  role: AIWorkloadRole;
  provider_id: UUID | null;
  provider_name: string | null;
  model: string | null;
  is_local: boolean | null;
  enabled: boolean;
  status: "configured" | "unconfigured" | "disabled" | "offline";
  embedding_dimension: number | null;
  legacy_fallback: boolean;
}

export interface AICapabilities {
  chat_available: boolean;
  embeddings_available: boolean;
  auto_tagging: boolean;
  auto_enrichment: boolean;
  warn_before_remote_chat: boolean;
  chat_is_local: boolean | null;
  privacy_mode: string;
}

export type AICapabilityStatus =
  | "available"
  | "unavailable"
  | "checking"
  | "not_configured";

export interface AICapabilityHealth {
  status: AICapabilityStatus;
  provider: string | null;
  model: string | null;
  latency_ms: number | null;
  last_checked: string | null;
  error: string | null;
}

export interface AIHealth {
  ocr: AICapabilityHealth;
  indexing: AICapabilityHealth;
  embedding: AICapabilityHealth;
  chat: AICapabilityHealth;
  auto_tagging: boolean;
  auto_enrichment: boolean;
}

export interface AIUsageSummary {
  range: "today" | "7d" | "30d" | "month";
  interval: "hour" | "day";
  timezone: "UTC";
  starts_at: string;
  ends_at: string;
  totals: {
    requests: number;
    input_tokens: number | null;
    output_tokens: number | null;
    duration_ms: number | null;
    estimated_cost: number | null;
    cost_currency: string | null;
    cost_coverage: "none" | "partial" | "complete" | "local_only";
  };
  time_series: Array<{
    bucket: string;
    requests: number;
    input_tokens: number | null;
    output_tokens: number | null;
    duration_ms: number | null;
  }>;
  by_provider: Array<{
    key: string;
    label: string;
    requests: number;
    input_tokens: number | null;
    output_tokens: number | null;
  }>;
  by_workload: Array<{
    key: string;
    label: string;
    requests: number;
    duration_ms?: number | null;
  }>;
}

export interface SystemSummary {
  version: string;
  schema_revision: string;
  process_uptime_seconds: number;
  deployment_mode: string;
  services: Record<string, string>;
  database_status: string;
  storage_status: string;
  worker_status: string;
  worker_last_seen_at: string | null;
  document_count: number;
  indexed_document_count: number;
  queued_jobs: number;
  running_jobs: number;
  runtime: Record<string, string | number | null>;
}

export interface StorageMetrics {
  configured_source: string | null;
  container_path: string;
  disk_total_bytes: number | null;
  disk_used_bytes: number | null;
  disk_free_bytes: number | null;
  folium_bytes: number | null;
  categories: Record<string, number | null>;
  database_bytes: number | null;
  database_categories: Record<string, number | null>;
  message: string;
}

export interface ApplicationLog {
  id: UUID;
  timestamp: string;
  level: string;
  service: string;
  module: string;
  message: string;
  request_id: string | null;
  context: Record<string, unknown>;
  stack_trace: string | null;
}

export interface ApplicationLogList {
  items: ApplicationLog[];
  total: number;
  page: number;
  page_size: number;
  retention_days: number;
}

export interface About {
  product: string;
  version: string;
  description: string;
  build_revision: string | null;
  build_date: string | null;
  project_links: Record<string, string>;
}

export interface Suggestion {
  id: UUID;
  document_id: UUID;
  field: string;
  value: Record<string, unknown>;
  status: string;
  provider: string | null;
  model: string | null;
  confidence: number | null;
}

export interface Health {
  status: string;
  version: string;
  instance_state?: string;
}

export interface StorageHealth {
  status: string;
  documents_ok: boolean;
  consume_ok: boolean;
  export_ok: boolean;
  documents_path: string;
  consume_path: string;
  export_path: string;
  message: string;
}

export interface Message {
  message: string;
}

export interface TestConnectionResult {
  message: string;
  status: "available" | "offline";
  latency_ms: number;
  model_count: number | null;
  tested_at: string;
}

export interface BackupRepositoryHealth {
  configured: boolean;
  exists: boolean;
  readable: boolean;
  writable: boolean;
  path: string;
  free_bytes: number | null;
  message: string;
}

export interface BackupSettings {
  enabled: boolean;
  schedule_type: "daily" | "weekly" | "interval_hours";
  backup_time: string;
  weekday: number | null;
  interval_hours: number | null;
  repository_subdir: string;
  retention_count: number;
  verify_after_backup: boolean;
  last_success_at: string | null;
  next_run_at: string | null;
  repository: BackupRepositoryHealth;
}

export interface BackupSettingsUpdate {
  enabled?: boolean;
  schedule_type?: "daily" | "weekly" | "interval_hours";
  backup_time?: string;
  weekday?: number | null;
  interval_hours?: number | null;
  repository_subdir?: string;
  retention_count?: number;
  verify_after_backup?: boolean;
}

export interface BackupRecord {
  id: UUID | null;
  filename: string;
  relative_key: string;
  created_at: string | null;
  completed_at: string | null;
  size_bytes: number | null;
  document_count: number | null;
  folium_version: string | null;
  schema_version: string | null;
  format_version: number | null;
  status: string;
  verification_status: string;
  verified_at: string | null;
  error_message: string | null;
  progress_stage: string | null;
}

export interface BackupInspect {
  manifest: Record<string, unknown>;
  verification_status: string;
  compatible: boolean;
  messages: string[];
}

export interface BackupRestoreStatus {
  active: boolean;
  stage: string;
  filename: string | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface BootstrapStatus {
  instance_state: string;
  ready: boolean;
}

export interface OnboardingStatus {
  required: boolean;
  current_version: number;
  completed_version: number;
}
