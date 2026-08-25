import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { api, clearSession, handleSessionResponse } from "./client";
import { documentNeedsProcessingPoll } from "@/features/documents/retrievalReadiness";
import type {
  AIProvider,
  AIProviderCreate,
  AIProviderUpdate,
  AIPolicy,
  AIPolicyUpdate,
  AIUsageSummary,
  AIAssignment,
  AICapabilities,
  AIHealth,
  AIProviderModels,
  AIWorkloadRole,
  About,
  ApplicationLogList,
  AskRequest,
  AskResponse,
  AskConversation,
  BulkActionRequest,
  Document,
  DocumentList,
  DocumentListParams,
  DocumentMetadataUpdate,
  DocumentMoveRequest,
  DocumentContent,
  DocumentProcessResult,
  Folder,
  FolderCreate,
  FolderDeleteRequest,
  FolderUpdate,
  InboxActivityList,
  InboxActivityParams,
  InboxOverviewMetrics,
  Job,
  LibraryOverview,
  LoginRequest,
  Message,
  NamedEntity,
  NamedEntityCreate,
  PasswordChangeRequest,
  ProfileUpdateRequest,
  RegisterRequest,
  SearchRequest,
  SearchResponse,
  Session,
  UserSession,
  ApiToken,
  ApiTokenCreated,
  StorageHealth,
  StorageMetrics,
  SystemSummary,
  Suggestion,
  Tag,
  TagCreate,
  TagMerge,
  TagUpdate,
  TestConnectionResult,
  User,
  UserAdmin,
  UserUsage,
  Invite,
  PasswordResetRequest,
  BackupSettings,
  BackupSettingsUpdate,
  BackupRecord,
  BackupInspect,
  BackupRestoreStatus,
  BootstrapStatus,
  OnboardingStatus,
} from "./types";

// ---- Query keys ----

export const queryKeys = {
  session: ["session"] as const,
  folders: ["folders"] as const,
  folder: (id: string) => ["folders", id] as const,
  tags: ["tags"] as const,
  documentTypes: ["document-types"] as const,
  correspondents: ["correspondents"] as const,
  documents: (params: DocumentListParams) => ["documents", params] as const,
  document: (id: string) => ["documents", id] as const,
  documentContent: (id: string) => ["documents", id, "content"] as const,
  askConversation: (documentId: string) =>
    ["documents", documentId, "ask-conversation"] as const,
  folderDocuments: (folderId: string, params: DocumentListParams) =>
    ["folders", folderId, "documents", params] as const,
  search: (req: SearchRequest) => ["search", req] as const,
  jobs: (status?: string, documentId?: string) =>
    ["jobs", status ?? "all", documentId ?? "all"] as const,
  job: (id: string) => ["jobs", id] as const,
  aiProviders: ["ai", "providers"] as const,
  aiPolicy: ["ai", "policy"] as const,
  aiUsage: ["ai", "usage"] as const,
  aiAssignments: ["ai", "assignments"] as const,
  aiCapabilities: ["ai", "capabilities"] as const,
  aiHealth: ["ai", "health"] as const,
  aiSuggestions: (documentId?: string) =>
    ["ai", "suggestions", documentId ?? "all"] as const,
  storageHealth: ["storage", "health"] as const,
  health: ["health"] as const,
  inboxOverview: ["inbox-overview"] as const,
  inboxActivity: (params: InboxActivityParams) => ["inbox-activity", params] as const,
  libraryOverview: ["library-overview"] as const,
  backupSettings: ["backups", "settings"] as const,
  backups: ["backups"] as const,
  backupRestoreStatus: ["backups", "restore-status"] as const,
  bootstrapStatus: ["bootstrap", "status"] as const,
  bootstrapBackups: ["bootstrap", "backups"] as const,
  onboardingStatus: ["onboarding", "status"] as const,
  apiTokens: ["auth", "api-tokens"] as const,
};

// ---- Auth ----

export function useSession(options?: Partial<UseQueryOptions<Session | null>>) {
  return useQuery({
    queryKey: queryKeys.session,
    queryFn: async () => {
      try {
        const session = await api.get<Session>("/api/auth/me");
        handleSessionResponse(session);
        return session;
      } catch {
        clearSession();
        return null;
      }
    },
    retry: false,
    staleTime: 5 * 60 * 1000,
    ...options,
  });
}

export function useLogin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: LoginRequest) => {
      const session = await api.post<Session>("/api/auth/login", data);
      handleSessionResponse(session);
      return session;
    },
    onSuccess: (session) => {
      qc.setQueryData(queryKeys.session, session);
    },
  });
}

export function useLogout() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Message>("/api/auth/logout"),
    onSuccess: () => {
      clearSession();
      qc.setQueryData(queryKeys.session, null);
      qc.clear();
    },
  });
}

export function useRegistrationStatus() {
  return useQuery({
    queryKey: ["auth", "registration-status"] as const,
    queryFn: () =>
      api.get<{ allow_registration: boolean }>("/api/auth/registration-status"),
    staleTime: 60_000,
  });
}

export function useRegister() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (data: RegisterRequest) => {
      const session = await api.post<Session>("/api/auth/register", data);
      handleSessionResponse(session);
      return session;
    },
    onSuccess: (session) => {
      qc.setQueryData(queryKeys.session, session);
    },
  });
}

export function useUpdateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: ProfileUpdateRequest) =>
      api.patch<User>("/api/auth/me", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.session }),
  });
}

export function useChangePassword() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: PasswordChangeRequest) =>
      api.post<Message>("/api/auth/me/password", data),
    onSuccess: () => {
      clearSession();
      qc.setQueryData(queryKeys.session, null);
      qc.clear();
    },
  });
}

export function useMyUsage() {
  return useQuery({
    queryKey: ["auth", "usage"] as const,
    queryFn: () => api.get<UserUsage>("/api/auth/me/usage"),
  });
}

export function useMySessions() {
  return useQuery({
    queryKey: ["auth", "sessions"] as const,
    queryFn: () => api.get<UserSession[]>("/api/auth/me/sessions"),
  });
}

export function useApiTokens() {
  return useQuery({
    queryKey: queryKeys.apiTokens,
    queryFn: () => api.get<ApiToken[]>("/api/auth/tokens"),
  });
}

export function useCreateApiToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      api.post<ApiTokenCreated>("/api/auth/tokens", { name }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.apiTokens }),
  });
}

export function useRevokeApiToken() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<Message>(`/api/auth/tokens/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.apiTokens }),
  });
}

export function useRevokeSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<Message>(`/api/auth/me/sessions/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auth", "sessions"] }),
  });
}

export function useSignOutOtherSessions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<Message>("/api/auth/me/sessions/sign-out-others"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["auth", "sessions"] }),
  });
}

export function useUploadAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.upload<User>("/api/auth/me/avatar", form);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.session }),
  });
}

export function useDeleteAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete<User>("/api/auth/me/avatar"),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.session }),
  });
}

export function useForgotPassword() {
  return useMutation({
    mutationFn: (username: string) =>
      api.post<{ message: string }>("/api/auth/forgot-password", { username }),
  });
}

export function useValidateResetToken(token: string | null) {
  return useQuery({
    queryKey: ["auth", "reset-validate", token] as const,
    queryFn: () =>
      api.get<{ valid: boolean; username: string | null }>(
        "/api/auth/reset-password/validate",
        { token },
      ),
    enabled: !!token,
    retry: false,
  });
}

export function useResetPassword() {
  return useMutation({
    mutationFn: (data: { token: string; new_password: string }) =>
      api.post<{ message: string }>("/api/auth/reset-password", data),
  });
}

export function useAdminUsers() {
  return useQuery({
    queryKey: ["users"] as const,
    queryFn: () => api.get<UserAdmin[]>("/api/users"),
  });
}

export function usePasswordResetRequests(enabled = true) {
  return useQuery({
    queryKey: ["password-resets"] as const,
    queryFn: () => api.get<PasswordResetRequest[]>("/api/users/password-resets"),
    refetchInterval: enabled ? 30_000 : false,
    enabled,
  });
}

export function useApprovePasswordReset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<PasswordResetRequest>(`/api/users/password-resets/${id}/approve`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["password-resets"] }),
  });
}

export function useRejectPasswordReset() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<{ message: string }>(`/api/users/password-resets/${id}/reject`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["password-resets"] }),
  });
}

export function useUpdateAdminUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: {
        is_admin?: boolean;
        is_active?: boolean;
        storage_quota_bytes?: number | null;
        ai_monthly_request_quota?: number | null;
        clear_storage_quota?: boolean;
        clear_ai_quota?: boolean;
      };
    }) => api.patch<UserAdmin>(`/api/users/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useDeleteAdminUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<Message>(`/api/users/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useAdminSetPassword() {
  return useMutation({
    mutationFn: ({ id, password }: { id: string; password: string }) =>
      api.post<Message>(`/api/users/${id}/password`, { password }),
  });
}

export function useCreateInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data?: {
      expires_in_hours?: number;
      storage_quota_bytes?: number | null;
      ai_monthly_request_quota?: number | null;
    }) => api.post<Invite>("/api/users/invites", data ?? {}),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invites"] }),
  });
}

export function useInvites() {
  return useQuery({
    queryKey: ["invites"] as const,
    queryFn: () => api.get<Invite[]>("/api/users/invites"),
  });
}

export function useRevokeInvite() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<Message>(`/api/users/invites/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["invites"] }),
  });
}

// ---- Folders ----

export function useFolders(trashed = false) {
  return useQuery({
    queryKey: trashed ? (["folders", "trashed"] as const) : queryKeys.folders,
    queryFn: () =>
      api.get<Folder[]>("/api/folders", trashed ? { trashed: true } : undefined),
  });
}

export function useFolder(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.folder(id ?? ""),
    queryFn: () => api.get<Folder>(`/api/folders/${id}`),
    enabled: !!id,
  });
}

export function useCreateFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: FolderCreate) => api.post<Folder>("/api/folders", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.folders }),
  });
}

export function useUpdateFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: FolderUpdate }) =>
      api.patch<Folder>(`/api/folders/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.folders }),
  });
}

export function useDeleteFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: FolderDeleteRequest }) =>
      api.delete<void>(`/api/folders/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["folders"] });
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["trash"] });
    },
  });
}

export function useTrashFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Folder>(`/api/folders/${id}/trash`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["folders"] });
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["trash"] });
    },
  });
}

export function useRestoreFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Folder>(`/api/folders/${id}/restore`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["folders"] });
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["trash"] });
    },
  });
}

export function usePurgeFolder() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<{ message: string }>(`/api/folders/${id}/purge`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["folders"] });
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["trash"] });
    },
  });
}

export function useTrashCount() {
  return useQuery({
    queryKey: ["trash", "count"] as const,
    queryFn: () =>
      api.get<{ documents: number; folders: number; total: number; retention_days: number }>(
        "/api/trash/count",
      ),
    refetchInterval: 15_000,
  });
}

export function useEmptyTrash() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ message: string }>("/api/trash/empty"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["folders"] });
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["trash"] });
    },
  });
}

// ---- Tags ----

export function useTags() {
  return useQuery({
    queryKey: queryKeys.tags,
    queryFn: () => api.get<Tag[]>("/api/tags"),
  });
}

export function useCreateTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: TagCreate) => api.post<Tag>("/api/tags", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.tags });
      qc.invalidateQueries({ queryKey: queryKeys.libraryOverview });
    },
  });
}

export function useUpdateTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: TagUpdate }) =>
      api.patch<Tag>(`/api/tags/${id}`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.tags });
      qc.invalidateQueries({ queryKey: queryKeys.libraryOverview });
    },
  });
}

export function useDeleteTag() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/api/tags/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.tags });
      qc.invalidateQueries({ queryKey: queryKeys.libraryOverview });
    },
  });
}

export function useMergeTags() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: TagMerge) => api.post<Tag>("/api/tags/merge", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.tags });
      qc.invalidateQueries({ queryKey: queryKeys.libraryOverview });
    },
  });
}

export function useDocumentTypes() {
  return useQuery({
    queryKey: queryKeys.documentTypes,
    queryFn: () => api.get<NamedEntity[]>("/api/document-types"),
  });
}

export function useCorrespondents() {
  return useQuery({
    queryKey: queryKeys.correspondents,
    queryFn: () => api.get<NamedEntity[]>("/api/correspondents"),
  });
}

export function useCreateDocumentType() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: NamedEntityCreate) =>
      api.post<NamedEntity>("/api/document-types", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.documentTypes }),
  });
}

export function useCreateCorrespondent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: NamedEntityCreate) =>
      api.post<NamedEntity>("/api/correspondents", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.correspondents }),
  });
}

// ---- Documents ----

function documentParamsToQuery(params: DocumentListParams): Record<string, string | number | boolean> {
  const q: Record<string, string | number | boolean> = {};
  if (params.folder_id) q.folder_id = params.folder_id;
  if (params.include_descendants) q.include_descendants = true;
  if (params.inbox !== undefined) q.inbox = params.inbox;
  if (params.inbox_status) q.inbox_status = params.inbox_status;
  if (params.trashed) q.trashed = true;
  if (params.unprocessed !== undefined) q.unprocessed = params.unprocessed;
  if (params.tag_ids?.length) q.tag_ids = params.tag_ids.join(",");
  if (params.q) q.q = params.q;
  if (params.page) q.page = params.page;
  if (params.page_size) q.page_size = params.page_size;
  if (params.sort) q.sort = params.sort;
  if (params.order) q.order = params.order;
  return q;
}

export function useDocuments(
  params: DocumentListParams = {},
  options?: Pick<
    UseQueryOptions<DocumentList, Error>,
    "refetchInterval" | "enabled" | "staleTime"
  >,
) {
  return useQuery({
    queryKey: queryKeys.documents(params),
    queryFn: () =>
      api.get<DocumentList>("/api/documents", documentParamsToQuery(params)),
    ...options,
  });
}

export function useInboxOverview(
  options?: Pick<UseQueryOptions<InboxOverviewMetrics, Error>, "refetchInterval" | "enabled">,
) {
  return useQuery({
    queryKey: queryKeys.inboxOverview,
    queryFn: () => api.get<InboxOverviewMetrics>("/api/inbox/overview"),
    ...options,
  });
}

export function useInboxActivity(
  params: InboxActivityParams,
  options?: Pick<
    UseQueryOptions<InboxActivityList, Error>,
    "refetchInterval" | "enabled"
  >,
) {
  return useQuery({
    queryKey: queryKeys.inboxActivity(params),
    queryFn: () => {
      const q: Record<string, string | number> = {};
      if (params.range_days) q.range_days = params.range_days;
      if (params.tab) q.tab = params.tab;
      if (params.q) q.q = params.q;
      if (params.page) q.page = params.page;
      if (params.page_size) q.page_size = params.page_size;
      return api.get<InboxActivityList>("/api/inbox/activity", q);
    },
    ...options,
  });
}

export function useLibraryOverview() {
  return useQuery({
    queryKey: queryKeys.libraryOverview,
    queryFn: () => api.get<LibraryOverview>("/api/library/overview"),
  });
}

export function useResetLibraryStatistics() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<LibraryOverview["activity"]>("/api/library/reset-statistics"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.libraryOverview });
      qc.invalidateQueries({ queryKey: queryKeys.inboxOverview });
    },
  });
}

export function useFolderDocuments(folderId: string | undefined, params: DocumentListParams = {}) {
  const merged = { ...params, folder_id: folderId };
  return useQuery({
    queryKey: queryKeys.folderDocuments(folderId ?? "", merged),
    queryFn: () =>
      api.get<DocumentList>(
        `/api/folders/${folderId}/documents`,
        documentParamsToQuery(params),
      ),
    enabled: !!folderId,
  });
}

export function useDocument(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.document(id ?? ""),
    queryFn: () => api.get<Document>(`/api/documents/${id}`),
    enabled: !!id,
    refetchInterval: (query) => {
      const doc = query.state.data;
      if (!doc) return false;
      return documentNeedsProcessingPoll(doc) ? 3_000 : false;
    },
  });
}

export function useDocumentContent(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.documentContent(id ?? ""),
    queryFn: () => api.get<DocumentContent>(`/api/documents/${id}/content`),
    enabled: !!id,
  });
}

export function useUpdateDocumentMetadata() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: DocumentMetadataUpdate }) =>
      api.patch<Document>(`/api/documents/${id}/metadata`, data),
    onSuccess: (doc) => {
      qc.setQueryData(queryKeys.document(doc.id), doc);
      qc.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}

export function useMoveDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: DocumentMoveRequest }) =>
      api.post<Document>(`/api/documents/${id}/move`, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: queryKeys.folders });
    },
  });
}

export function useTrashDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Document>(`/api/documents/${id}/trash`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: queryKeys.folders });
      qc.invalidateQueries({ queryKey: ["trash"] });
    },
  });
}

export function useRestoreDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Document>(`/api/documents/${id}/restore`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: queryKeys.folders });
      qc.invalidateQueries({ queryKey: ["trash"] });
    },
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/api/documents/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["trash"] });
    },
  });
}

export function useBulkAction() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: BulkActionRequest) =>
      api.post<Message>("/api/documents/bulk", data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: queryKeys.folders });
      qc.invalidateQueries({ queryKey: queryKeys.tags });
      qc.invalidateQueries({ queryKey: ["trash"] });
      qc.invalidateQueries({ queryKey: ["inbox-count"] });
    },
  });
}

export function useProcessInboxDocuments() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (document_ids: string[]) =>
      api.post<DocumentProcessResult>("/api/documents/process", { document_ids }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: queryKeys.folders });
      qc.invalidateQueries({ queryKey: ["inbox-count"] });
      qc.invalidateQueries({ queryKey: ["inbox-overview"] });
      qc.invalidateQueries({ queryKey: ["inbox-activity"] });
    },
  });
}

export function useRemoveFromQueue() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (document_ids: string[]) =>
      api.post<Message>("/api/documents/remove-from-queue", { document_ids }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["inbox-count"] });
      qc.invalidateQueries({ queryKey: ["inbox-overview"] });
      qc.invalidateQueries({ queryKey: ["inbox-activity"] });
    },
  });
}

export function useRetryPreflight() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<Document>(`/api/documents/${id}/retry-preflight`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["inbox-overview"] });
      qc.invalidateQueries({ queryKey: ["inbox-activity"] });
    },
  });
}

export function useRetryOcr() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Document>(`/api/documents/${id}/retry-ocr`),
    onSuccess: (doc) => {
      qc.setQueryData(queryKeys.document(doc.id), doc);
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: queryKeys.documentContent(doc.id) });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function useReprocessEmbeddings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<Document>(`/api/documents/${id}/reprocess-embeddings`),
    onSuccess: (doc) => {
      qc.setQueryData(queryKeys.document(doc.id), doc);
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export function useReprocessSuggestions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<Document>(`/api/documents/${id}/reprocess-suggestions`),
    onSuccess: (doc) => {
      qc.setQueryData(queryKeys.document(doc.id), doc);
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
      qc.invalidateQueries({ queryKey: queryKeys.aiSuggestions(doc.id) });
      qc.invalidateQueries({ queryKey: queryKeys.aiSuggestions() });
    },
  });
}

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ file, folderId }: { file: File; folderId?: string }) => {
      const form = new FormData();
      form.append("file", file);
      if (folderId) form.append("folder_id", folderId);
      return api.upload<Document>("/api/documents/upload", form);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: queryKeys.folders });
    },
  });
}

// ---- Search ----

export function useSearch(request: SearchRequest, enabled = true) {
  return useQuery({
    queryKey: queryKeys.search(request),
    queryFn: ({ signal }) => api.post<SearchResponse>("/api/search", request, { signal }),
    enabled: enabled && !!request.query?.trim(),
    placeholderData: (prev) => prev,
  });
}

export function useSearchMutation() {
  return useMutation({
    mutationFn: (request: SearchRequest) =>
      api.post<SearchResponse>("/api/search", request),
  });
}

// ---- Ask ----

export function useAskConversation(documentId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.askConversation(documentId ?? ""),
    queryFn: () =>
      api.get<AskConversation>(`/api/documents/${documentId}/ask/conversation`),
    enabled: Boolean(documentId),
  });
}

export function useAskDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      documentId,
      signal,
      ...body
    }: AskRequest & { documentId: string; signal?: AbortSignal }) =>
      api.post<AskResponse>(`/api/documents/${documentId}/ask`, body, { signal }),
    onSuccess: (_data, vars) => {
      void qc.invalidateQueries({
        queryKey: queryKeys.askConversation(vars.documentId),
      });
    },
  });
}

export function useNewAskConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) =>
      api.post<AskConversation>(
        `/api/documents/${documentId}/ask/conversation/new`,
        {},
      ),
    onSuccess: (data, documentId) => {
      qc.setQueryData(queryKeys.askConversation(documentId), data);
    },
  });
}

export function useClearAskConversation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (documentId: string) =>
      api.delete<{ message: string }>(
        `/api/documents/${documentId}/ask/conversation`,
      ),
    onSuccess: (_data, documentId) => {
      qc.setQueryData(queryKeys.askConversation(documentId), {
        id: null,
        document_id: documentId,
        messages: [],
        updated_at: null,
      } satisfies AskConversation);
    },
  });
}

export function useAsk() {
  return useMutation({
    mutationFn: (body: AskRequest) => api.post<AskResponse>("/api/ask", body),
  });
}

// ---- Jobs ----

export function useJobs(
  status?: string,
  documentId?: string,
  options?: Pick<UseQueryOptions<Job[], Error>, "refetchInterval">,
) {
  return useQuery({
    queryKey: queryKeys.jobs(status, documentId),
    queryFn: () =>
      api.get<Job[]>("/api/jobs", {
        ...(status ? { status } : {}),
        ...(documentId ? { document_id: documentId } : {}),
      }),
    refetchInterval: options?.refetchInterval ?? 5000,
  });
}

export function useJob(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.job(id ?? ""),
    queryFn: () => api.get<Job>(`/api/jobs/${id}`),
    enabled: !!id,
    refetchInterval: 3000,
  });
}

export function useCancelJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<Job>(`/api/jobs/${id}/cancel`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

// ---- AI ----

export function useAIProviders() {
  return useQuery({
    queryKey: queryKeys.aiProviders,
    queryFn: () => api.get<AIProvider[]>("/api/ai/providers"),
  });
}

export function useCreateAIProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AIProviderCreate) =>
      api.post<AIProvider>("/api/ai/providers", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.aiProviders }),
  });
}

export function useUpdateAIProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: AIProviderUpdate }) =>
      api.patch<AIProvider>(`/api/ai/providers/${id}`, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.aiProviders }),
  });
}

export function useDeleteAIProvider() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/api/ai/providers/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.aiProviders }),
  });
}

export function useTestAIProvider() {
  return useMutation({
    mutationFn: (id: string) =>
      api.post<TestConnectionResult>(`/api/ai/providers/${id}/test`),
  });
}

export function useAIPolicy() {
  return useQuery({
    queryKey: queryKeys.aiPolicy,
    queryFn: () => api.get<AIPolicy>("/api/ai/policy"),
  });
}

export function useUpdateAIPolicy() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: AIPolicyUpdate) =>
      api.patch<AIPolicy>("/api/ai/policy", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.aiPolicy }),
  });
}

export function useAIUsage(range: "today" | "7d" | "30d" | "month" = "month") {
  return useQuery({
    queryKey: [...queryKeys.aiUsage, range],
    queryFn: () => api.get<AIUsageSummary>("/api/ai/usage", { range }),
  });
}

export function useAIAssignments(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: queryKeys.aiAssignments,
    queryFn: () => api.get<AIAssignment[]>("/api/ai/assignments"),
    enabled: options?.enabled ?? true,
  });
}

export function useUpdateAIAssignment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { role: AIWorkloadRole; provider_id: string | null; model: string | null }) =>
      api.patch<AIAssignment>("/api/ai/assignments", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.aiAssignments }),
  });
}

export function useProviderModels(providerId: string | null) {
  return useQuery({
    queryKey: ["ai", "providers", providerId, "models"],
    queryFn: () => api.get<AIProviderModels>(`/api/ai/providers/${providerId}/models`),
    enabled: Boolean(providerId),
    retry: false,
  });
}

export function useAICapabilities() {
  return useQuery({
    queryKey: queryKeys.aiCapabilities,
    queryFn: () => api.get<AICapabilities>("/api/ai/capabilities"),
  });
}

export function useAIHealth() {
  return useQuery({
    queryKey: queryKeys.aiHealth,
    queryFn: () => api.get<AIHealth>("/api/ai/health"),
    refetchInterval: 3_000,
    staleTime: 3_000,
  });
}

export function usePendingSuggestions(enabled = true) {
  return useQuery({
    queryKey: queryKeys.aiSuggestions(),
    queryFn: () =>
      api.get<Suggestion[]>("/api/ai/suggestions", {
        status: "pending",
      }),
    enabled,
    refetchInterval: 4_000,
  });
}

export function useDocumentSuggestions(documentId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.aiSuggestions(documentId),
    queryFn: () =>
      api.get<Suggestion[]>("/api/ai/suggestions", {
        document_id: documentId!,
        status: "pending",
      }),
    enabled: Boolean(documentId),
    refetchInterval: (query) => {
      const rows = query.state.data;
      return rows && rows.length > 0 ? false : 4_000;
    },
  });
}

export function useAcceptSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<Suggestion>(`/api/ai/suggestions/${id}/accept`),
    onSuccess: (suggestion) => {
      qc.invalidateQueries({ queryKey: ["ai", "suggestions"] });
      qc.invalidateQueries({ queryKey: ["documents"] });
      qc.invalidateQueries({ queryKey: queryKeys.document(suggestion.document_id) });
      qc.invalidateQueries({ queryKey: queryKeys.tags });
      qc.invalidateQueries({ queryKey: queryKeys.folders });
    },
  });
}

export function useRejectSuggestion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<Suggestion>(`/api/ai/suggestions/${id}/reject`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["ai", "suggestions"] });
    },
  });
}

// ---- Health / Storage ----

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: () => api.get<{ status: string; version: string }>("/health"),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: 1,
  });
}

export function useStorageHealth() {
  return useQuery({
    queryKey: queryKeys.storageHealth,
    queryFn: () => api.get<StorageHealth>("/health/storage"),
  });
}

export function useSystemSummary() {
  return useQuery({
    queryKey: ["system", "summary"],
    queryFn: () => api.get<SystemSummary>("/api/system/summary"),
    refetchInterval: 30_000,
  });
}

export function useStorageMetrics() {
  return useQuery({
    queryKey: ["system", "storage"],
    queryFn: () => api.get<StorageMetrics>("/api/system/storage"),
  });
}

export function useDiagnostics() {
  return useMutation({
    mutationFn: () => api.get<{ generated_at: string; text: string }>("/api/system/diagnostics"),
  });
}

export interface LogFilters {
  search?: string;
  level?: string;
  service?: string;
  range?: string;
  page?: number;
}

export function useApplicationLogs(filters: LogFilters, live = false) {
  return useQuery({
    queryKey: ["logs", filters],
    queryFn: () => api.get<ApplicationLogList>("/api/logs", { ...filters, page_size: 50 }),
    placeholderData: (previous) => previous,
    refetchInterval: (query) =>
      live && query.state.fetchFailureCount < 3 ? 5_000 : false,
  });
}

export function useClearApplicationLogs() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.delete<Message>("/api/logs"),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["logs"] }),
  });
}

export function useAbout() {
  return useQuery({
    queryKey: ["about"],
    queryFn: () => api.get<About>("/api/about"),
    staleTime: Infinity,
  });
}

// ---- Inbox count ----

export function useInboxCount() {
  return useQuery({
    queryKey: ["inbox-count"],
    queryFn: async () => {
      const result = await api.get<DocumentList>("/api/documents", {
        inbox: true,
        page_size: 1,
      });
      return result.total;
    },
    staleTime: 30_000,
  });
}

export function useBootstrapStatus() {
  return useQuery({
    queryKey: queryKeys.bootstrapStatus,
    queryFn: () => api.get<BootstrapStatus>("/api/bootstrap/status"),
    retry: 1,
    staleTime: 5_000,
    refetchInterval: (query) => {
      const state = query.state.data?.instance_state;
      return state && state !== "ready" ? 2000 : false;
    },
  });
}

export function useOnboardingStatus(enabled = true) {
  return useQuery({
    queryKey: queryKeys.onboardingStatus,
    queryFn: () => api.get<OnboardingStatus>("/api/onboarding/status"),
    enabled,
    staleTime: 5_000,
  });
}

export function useCompleteOnboarding() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<OnboardingStatus>("/api/onboarding/complete"),
    onSuccess: (status) => qc.setQueryData(queryKeys.onboardingStatus, status),
  });
}

export function useBootstrapBackups(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.bootstrapBackups,
    queryFn: () => api.get<BackupRecord[]>("/api/bootstrap/backups"),
    enabled,
  });
}

export function useBootstrapSetup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<BootstrapStatus>("/api/bootstrap/setup"),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.bootstrapStatus }),
  });
}

export function useBootstrapInspect() {
  return useMutation({
    mutationFn: (filename: string) =>
      api.post<BackupInspect>("/api/bootstrap/backups/inspect", { filename }),
  });
}

export function useBootstrapRestore() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (filename: string) =>
      api.post<{ status: string; stage: string }>("/api/bootstrap/restore", {
        filename,
        confirm: true,
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.bootstrapStatus }),
  });
}

export function useBackupSettings() {
  return useQuery({
    queryKey: queryKeys.backupSettings,
    queryFn: () => api.get<BackupSettings>("/api/backups/settings"),
  });
}

export function useUpdateBackupSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: BackupSettingsUpdate) =>
      api.patch<BackupSettings>("/api/backups/settings", data),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.backupSettings }),
  });
}

export function useBackups(options?: { refetchInterval?: number | false }) {
  return useQuery({
    queryKey: queryKeys.backups,
    queryFn: () => api.get<BackupRecord[]>("/api/backups"),
    refetchInterval: options?.refetchInterval,
  });
}

export function useCreateBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<BackupRecord>("/api/backups"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.backups });
      qc.invalidateQueries({ queryKey: queryKeys.backupSettings });
    },
  });
}

export function useVerifyBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.post<BackupRecord>(`/api/backups/${id}/verify`),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.backups }),
  });
}

export function useDeleteBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/api/backups/${id}`, { confirm: true }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.backups }),
  });
}

export function useInspectBackup() {
  return useMutation({
    mutationFn: (id: string) => api.get<BackupInspect>(`/api/backups/${id}/inspect`),
  });
}

export function useRestoreBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) =>
      api.post<BackupRestoreStatus>(`/api/backups/${id}/restore`, { confirm: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.backupRestoreStatus });
      qc.invalidateQueries({ queryKey: queryKeys.backups });
    },
  });
}

export function useBackupRestoreStatus(enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.backupRestoreStatus,
    queryFn: () => api.get<BackupRestoreStatus>("/api/backups/restore/status"),
    enabled,
    refetchInterval: enabled ? 2000 : false,
  });
}
