import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowUpDown,
  CheckCheck,
  RefreshCw,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import {
  useAIHealth,
  useDocuments,
  useJobs,
  usePendingSuggestions,
  useProcessInboxDocuments,
  useRemoveFromQueue,
  useReprocessSuggestions,
  useRetryPreflight,
} from "@/lib/api/hooks";
import type { Document, InboxStatus, Suggestion } from "@/lib/api/types";
import type { useDocumentUploader } from "@/lib/api/upload";
import type { UploadEntry } from "@/lib/uploadTree";
import { cn } from "@/lib/utils";
import { UploadDropzone } from "@/components/documents/UploadDropzone";
import { Button } from "@/components/ui/Button";
import { Checkbox } from "@/components/ui/Checkbox";
import { Input } from "@/components/ui/Input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { InboxPreviewDialog } from "./InboxPreviewDialog";
import { InboxProgressBar } from "./InboxProgressBar";
import { InboxReviewCard } from "./InboxReviewCard";
import { InboxRejectedCard } from "./InboxRejectedCard";
import { inboxAiFilingState } from "./inboxAiFiling";
import { inboxBatchProgress } from "./inboxPreparingPhases";
import {
  canRetrySuggestions,
  isDocSettled,
  visibleSelectedDocs,
} from "./inboxReviewActions";
import { InboxToast } from "./InboxToast";
import { acceptAllSuggestions } from "./acceptAllSuggestions";
import { isSystemInboxPath } from "./formatMeta";
import { suggestionJobStatusForDoc } from "./suggestionJobStatus";
import type { SessionRejection } from "./sessionRejections";

type StatusTab = "all" | InboxStatus;
type DocumentUploader = ReturnType<typeof useDocumentUploader>;

const STATUS_TABS: { id: StatusTab; label: string }[] = [
  { id: "all", label: "All" },
  { id: "preparing", label: "Preparing" },
  { id: "needs_review", label: "Needs review" },
  { id: "ready", label: "Ready" },
  { id: "failed", label: "Failed" },
];

const SORT_OPTIONS = [
  { value: "added_date", label: "Date added" },
  { value: "modified_date", label: "Modified" },
  { value: "title", label: "Title" },
];

function isProcessable(doc: Document): boolean {
  if (doc.inbox_status === "preparing" || doc.inbox_status === "failed") return false;
  if (doc.pending_folder_path) return true;
  if (doc.folder_path && !isSystemInboxPath(doc.folder_path)) return true;
  return false;
}

interface InboxWorkViewProps {
  uploader: DocumentUploader;
  sessionRejections: SessionRejection[];
  onDismissRejection: (id: string) => void;
  onClearRejections: () => void;
  toastMessage: string | null;
  onDismissToast: () => void;
  onUploadFinished?: () => void;
}

export function InboxWorkView({
  uploader,
  sessionRejections,
  onDismissRejection,
  onClearRejections,
  toastMessage,
  onDismissToast,
  onUploadFinished,
}: InboxWorkViewProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [searchQuery, setSearchQuery] = useState("");
  const [statusTab, setStatusTab] = useState<StatusTab>("all");
  const [sort, setSort] = useState("added_date");
  const [order, setOrder] = useState<"asc" | "desc">("asc");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [removeIds, setRemoveIds] = useState<string[] | null>(null);
  const [resultMsg, setResultMsg] = useState<string | null>(null);
  const [acceptAllBusy, setAcceptAllBusy] = useState(false);
  const [retryBatchBusy, setRetryBatchBusy] = useState(false);
  const [expandedIds, setExpandedIds] = useState<Set<string> | null>(null);

  const listParams = {
    inbox: true as const,
    q: searchQuery || undefined,
    inbox_status: statusTab === "all" ? undefined : statusTab,
    sort: sort as "added_date" | "title" | "modified_date" | "created_date",
    order,
    page_size: 100,
  };

  const pollWhilePreparing = (query: {
    state: { data?: { items?: Document[] } };
  }) => {
    const items = query.state.data?.items ?? [];
    const busy = items.some(
      (d) =>
        d.inbox_status === "preparing" ||
        d.processing_status === "pending" ||
        d.processing_status === "processing",
    );
    if (!busy) return false;
    const ocrLive = items.some(
      (d) =>
        d.inbox_status === "preparing" &&
        d.ocr_pages_total != null &&
        d.ocr_pages_total > 0,
    );
    return ocrLive ? 2000 : 3000;
  };

  const { data: docList, isLoading, refetch, isFetching } = useDocuments(
    listParams,
    { refetchInterval: pollWhilePreparing },
  );
  const { data: allInbox } = useDocuments(
    { inbox: true, page_size: 100 },
    { refetchInterval: pollWhilePreparing },
  );
  const { data: aiHealth } = useAIHealth();
  const { aiSuggestionsAvailable, reason: filingReason } = inboxAiFilingState(aiHealth);
  const { data: pendingSuggestions = [] } = usePendingSuggestions(aiSuggestionsAvailable);
  const { data: inboxJobs = [] } = useJobs(undefined, undefined, {
    refetchInterval: (query) => {
      const jobs = query.state.data ?? [];
      const ocrRunning = jobs.some(
        (j) =>
          (j.job_type === "ocr" || j.job_type === "text_extraction") &&
          j.status === "running",
      );
      return ocrRunning ? 2500 : 5000;
    },
  });

  const processDocs = useProcessInboxDocuments();
  const removeFromQueue = useRemoveFromQueue();
  const retryPreflight = useRetryPreflight();
  const reprocessSuggestions = useReprocessSuggestions();

  const documents = docList?.items ?? [];
  const documentIds = documents.map((d) => d.id);
  const documentsById = useMemo(
    () => new Map(documents.map((d) => [d.id, d])),
    [documents],
  );

  const suggestionsByDoc = useMemo(() => {
    const map: Record<string, Suggestion[]> = {};
    for (const s of pendingSuggestions) {
      (map[s.document_id] ??= []).push(s);
    }
    return map;
  }, [pendingSuggestions]);

  const batchProgress = useMemo(
    () => inboxBatchProgress(allInbox?.items ?? [], inboxJobs),
    [allInbox?.items, inboxJobs],
  );

  const counts = useMemo(() => {
    const items = allInbox?.items ?? [];
    const c: Record<StatusTab, number> = {
      all: items.length,
      ready: 0,
      needs_review: 0,
      failed: 0,
      preparing: 0,
    };
    for (const d of items) {
      const s = d.inbox_status;
      if (s) c[s] += 1;
    }
    c.failed += sessionRejections.length;
    c.all += sessionRejections.length;
    return c;
  }, [allInbox?.items, sessionRejections.length]);

  const selectedDocs = visibleSelectedDocs(documents, selectedIds);
  const hasVisibleSelection = selectedDocs.length > 0;
  const processTargets = hasVisibleSelection
    ? selectedDocs.filter(isProcessable)
    : documents.filter(isProcessable);
  const processCount = processTargets.length;

  const acceptScopeIds = hasVisibleSelection
    ? selectedDocs.map((d) => d.id)
    : documentIds;
  const pendingInScope = pendingSuggestions.filter((s) =>
    acceptScopeIds.includes(s.document_id),
  );

  const showRejectedInList = statusTab === "all" || statusTab === "failed";

  const allVisibleSelected =
    documents.length > 0 && documents.every((d) => selectedIds.has(d.id));
  const someVisibleSelected = documents.some((d) => selectedIds.has(d.id));
  const retrySuggestionTargets = selectedDocs.filter(canRetrySuggestions);

  // Always start collapsed.
  useEffect(() => {
    if (documents.length === 0) return;
    if (expandedIds === null) {
      setExpandedIds(new Set());
    }
  }, [documents.length, expandedIds]);

  const toggleExpand = (id: string) => {
    const doc = documents.find((d) => d.id === id);
    if (!doc || !isDocSettled(doc)) return;
    setExpandedIds((prev) => {
      const base = prev ?? new Set<string>();
      const next = new Set(base);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAllVisible = () => {
    if (allVisibleSelected) {
      setSelectedIds(new Set());
      return;
    }
    setSelectedIds(new Set(documents.map((d) => d.id)));
  };

  useEffect(() => {
    if (searchParams.get("upload") !== "1") return;
    const timer = window.setTimeout(() => {
      fileInputRef.current?.click();
      const next = new URLSearchParams(searchParams);
      next.delete("upload");
      setSearchParams(next, { replace: true });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [searchParams, setSearchParams]);

  const afterUpload = async (run: () => Promise<unknown>) => {
    await run();
    onUploadFinished?.();
    refetch();
  };

  const handleUploadFiles = async (files: FileList) => {
    await afterUpload(() => uploader.uploadFileList(files));
  };

  const handleEntries = async (entries: UploadEntry[]) => {
    await afterUpload(() => uploader.uploadEntries(entries));
  };

  const confirmRemove = async () => {
    if (!removeIds?.length) return;
    await removeFromQueue.mutateAsync(removeIds);
    setSelectedIds((prev) => {
      const next = new Set(prev);
      for (const id of removeIds) next.delete(id);
      return next;
    });
    if (previewId && removeIds.includes(previewId)) setPreviewId(null);
    setRemoveIds(null);
    setResultMsg(
      removeIds.length === 1
        ? "Removed 1 document from the queue."
        : `Removed ${removeIds.length} documents from the queue.`,
    );
    refetch();
  };

  const handleProcess = async () => {
    if (processCount === 0) return;
    try {
      const result = await processDocs.mutateAsync(processTargets.map((d) => d.id));
      setSelectedIds(new Set());
      const processedIds = result.processed.map((p) => p.id);
      if (processedIds.length > 0) {
        onClearRejections();
        navigate("/inbox", { state: { justProcessedIds: processedIds } });
        return;
      }
      const parts = [
        result.skipped.length ? `${result.skipped.length} skipped` : null,
        result.failed.length ? `${result.failed.length} failed` : null,
      ].filter(Boolean);
      setResultMsg(parts.join(" · ") || "Nothing processed");
      refetch();
    } catch (err) {
      setResultMsg(err instanceof Error ? err.message : "Process failed");
    }
  };

  const handleAcceptAll = async () => {
    if (pendingInScope.length === 0) return;
    setAcceptAllBusy(true);
    try {
      const { accepted, failed, skipped } = await acceptAllSuggestions(
        pendingSuggestions,
        acceptScopeIds,
        documentsById,
      );
      await queryClient.invalidateQueries({ queryKey: ["ai", "suggestions"] });
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
      await queryClient.invalidateQueries({ queryKey: ["folders"] });
      await queryClient.invalidateQueries({ queryKey: ["tags"] });
      const parts = [
        accepted ? `Accepted ${accepted} suggestion${accepted === 1 ? "" : "s"}` : null,
        skipped ? `${skipped} skipped (already edited)` : null,
        failed ? `${failed} failed` : null,
      ].filter(Boolean);
      setResultMsg(parts.join(" · ") || "No suggestions accepted");
      refetch();
    } finally {
      setAcceptAllBusy(false);
    }
  };

  const handleRetrySuggestionsBatch = async () => {
    if (!aiSuggestionsAvailable || retrySuggestionTargets.length === 0) return;
    setRetryBatchBusy(true);
    let retried = 0;
    let failed = 0;
    const skipped = selectedDocs.length - retrySuggestionTargets.length;
    try {
      for (const doc of retrySuggestionTargets) {
        try {
          await reprocessSuggestions.mutateAsync(doc.id);
          retried += 1;
        } catch {
          failed += 1;
        }
      }
      const parts = [
        retried ? `Retried suggestions for ${retried} document${retried === 1 ? "" : "s"}` : null,
        skipped ? `${skipped} skipped` : null,
        failed ? `${failed} failed` : null,
      ].filter(Boolean);
      setResultMsg(parts.join(" · ") || "No suggestions retried");
      refetch();
    } finally {
      setRetryBatchBusy(false);
    }
  };

  const handleAcceptAllForDoc = async (documentId: string) => {
    const pending = pendingSuggestions.filter((s) => s.document_id === documentId);
    if (pending.length === 0) return;
    setAcceptAllBusy(true);
    try {
      const { accepted, failed, skipped } = await acceptAllSuggestions(
        pending,
        [documentId],
        documentsById,
      );
      await queryClient.invalidateQueries({ queryKey: ["ai", "suggestions"] });
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
      await queryClient.invalidateQueries({ queryKey: ["folders"] });
      await queryClient.invalidateQueries({ queryKey: ["tags"] });
      const parts = [
        accepted ? `Accepted ${accepted} suggestion${accepted === 1 ? "" : "s"}` : null,
        skipped ? `${skipped} skipped (already edited)` : null,
        failed ? `${failed} failed` : null,
      ].filter(Boolean);
      setResultMsg(parts.join(" · ") || "No suggestions accepted");
      refetch();
    } finally {
      setAcceptAllBusy(false);
    }
  };

  const goBack = () => {
    onClearRejections();
    navigate("/inbox");
  };

  const emptyCopy =
    statusTab === "failed"
      ? {
          title: "No failed documents",
          body: "No documents in this view have failed.",
        }
      : {
          title: "Nothing to review",
          body: "Documents that require review and filing will appear here.",
        };

  return (
    <UploadDropzone
      onEntries={(entries) => void handleEntries(entries)}
      className="h-full"
      disabled={uploader.busy}
    >
      <input
        ref={fileInputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => e.target.files && void handleUploadFiles(e.target.files)}
      />
      <input
        ref={folderInputRef}
        type="file"
        className="hidden"
        // @ts-expect-error webkitdirectory is non-standard but widely supported
        webkitdirectory=""
        directory=""
        multiple
        onChange={(e) => e.target.files && void handleUploadFiles(e.target.files)}
      />

      <div className="flex h-full flex-col overflow-auto bg-[#F8FAFB]">
        <div className="px-6 pb-7 pt-[18px]">
          <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
            <div>
              <Button
                size="sm"
                variant="ghost"
                className="-ml-1 h-7 px-1.5 text-[#42515D]"
                onClick={goBack}
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                Back to Inbox
              </Button>
              <h1 className="mt-1 text-lg font-bold text-[#14212B]">Review & file</h1>
              <p className="mt-0.5 text-xs text-[#5D6B76]">
                Documents awaiting review and filing
                {isFetching ? " · refreshing…" : ""}
              </p>
              {!aiSuggestionsAvailable && (
                <p className="mt-1 text-[11px] text-[#74828D]">
                  {filingReason === "controls_off" ? (
                    <>
                      A filing model is assigned, but AI filing is turned off in{" "}
                      <Link
                        className="font-medium text-accent hover:underline"
                        to="/settings/artificial-intelligence?tab=controls"
                      >
                        AI → Controls
                      </Link>
                      . Use Manual filing on each document, or process from the toolbar
                      when a destination is set.
                    </>
                  ) : (
                    <>
                      Assign a filing model in{" "}
                      <Link
                        className="font-medium text-accent hover:underline"
                        to="/settings/artificial-intelligence?tab=models"
                      >
                        AI → Models
                      </Link>
                      . Use Manual filing on each document, or process from the toolbar
                      when a destination is set.
                    </>
                  )}
                </p>
              )}
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-9 rounded-lg"
                  disabled={uploader.busy}
                >
                  <Upload className="h-3.5 w-3.5" />
                  {uploader.busy ? "Uploading…" : "Upload"}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={() => fileInputRef.current?.click()}>
                  Upload files…
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => folderInputRef.current?.click()}>
                  Upload folder…
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3.5">
            <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2.5">
              <div className="relative w-[312px] max-w-full">
                <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#74828D]" />
                <Input
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  placeholder="Search inbox..."
                  className="h-9 rounded-lg border-[#DCE3E8] bg-white pl-9 text-xs"
                />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {STATUS_TABS.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => setStatusTab(tab.id)}
                    className={cn(
                      "h-[34px] rounded-lg border px-3 text-xs transition-colors",
                      statusTab === tab.id
                        ? "border-accent bg-accent-muted font-semibold text-accent"
                        : "border-[#DCE3E8] bg-white text-[#42515D] hover:bg-[#F8FAFB]",
                    )}
                  >
                    {tab.label}
                    <span className="ml-1 opacity-70">{counts[tab.id]}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="sm" variant="ghost" className="h-[34px] text-[#24333D]">
                    <ArrowUpDown className="h-3.5 w-3.5" />
                    Sort
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {SORT_OPTIONS.map((opt) => (
                    <DropdownMenuItem
                      key={opt.value}
                      onClick={() => {
                        if (sort === opt.value) {
                          setOrder((o) => (o === "asc" ? "desc" : "asc"));
                        } else {
                          setSort(opt.value);
                          setOrder("desc");
                        }
                      }}
                    >
                      {opt.label}
                      {sort === opt.value ? (order === "asc" ? " ↑" : " ↓") : ""}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>

              <Button
                size="sm"
                variant="outline"
                className="h-[38px] rounded-lg"
                disabled={
                  !aiSuggestionsAvailable ||
                  pendingInScope.length === 0 ||
                  acceptAllBusy
                }
                onClick={() => void handleAcceptAll()}
              >
                <CheckCheck className="h-3.5 w-3.5" />
                Accept all AI suggestions
                {pendingInScope.length > 0 ? ` (${pendingInScope.length})` : ""}
              </Button>

              <Button
                className="h-[38px] rounded-lg bg-accent px-4 font-semibold text-accent-foreground hover:bg-accent-hover"
                disabled={processCount === 0 || processDocs.isPending}
                onClick={() => void handleProcess()}
              >
                Process {processCount} document{processCount === 1 ? "" : "s"}
              </Button>
            </div>
          </div>

          {batchProgress.visible && (
            <div className="mb-1 mt-3">
              <div className="flex items-baseline justify-between gap-3">
                <h2 className="text-sm font-semibold text-[#14212B]">
                  Processing documents
                </h2>
                <p className="text-xs font-medium text-[#5D6B76]">
                  {batchProgress.completed} / {batchProgress.total} · {batchProgress.percent}%
                </p>
              </div>
              <InboxProgressBar percent={batchProgress.percent} className="mt-2" />
              <p className="mt-1.5 text-xs text-[#74828D]">
                OCR {batchProgress.active} active · {batchProgress.completed} completed ·{" "}
                {batchProgress.queued} queued
              </p>
            </div>
          )}

          <div className="mb-2.5 mt-2.5 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2.5 text-xs font-medium text-[#5D6B76]">
              <Checkbox
                checked={
                  allVisibleSelected ? true : someVisibleSelected ? "indeterminate" : false
                }
                onCheckedChange={() => toggleSelectAllVisible()}
                aria-label="Select all visible documents"
                disabled={documents.length === 0}
              />
              <span>
                {documents.length} document{documents.length === 1 ? "" : "s"}
                {showRejectedInList && sessionRejections.length > 0
                  ? ` · ${sessionRejections.length} rejected`
                  : ""}
                {selectedDocs.length > 0 ? ` · ${selectedDocs.length} selected` : ""}
              </span>
            </div>
            {selectedDocs.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 rounded-lg"
                  onClick={() => setRemoveIds(selectedDocs.map((d) => d.id))}
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Remove
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 rounded-lg"
                  disabled={
                    !aiSuggestionsAvailable ||
                    retrySuggestionTargets.length === 0 ||
                    retryBatchBusy
                  }
                  onClick={() => void handleRetrySuggestionsBatch()}
                >
                  <RefreshCw
                    className={cn("h-3.5 w-3.5", retryBatchBusy && "animate-spin")}
                  />
                  Retry suggestions
                  {retrySuggestionTargets.length > 0
                    ? ` (${retrySuggestionTargets.length})`
                    : ""}
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-8 rounded-lg"
                  disabled={
                    !aiSuggestionsAvailable ||
                    pendingInScope.length === 0 ||
                    acceptAllBusy
                  }
                  onClick={() => void handleAcceptAll()}
                >
                  <CheckCheck className="h-3.5 w-3.5" />
                  Accept AI suggestions
                  {pendingInScope.length > 0 ? ` (${pendingInScope.length})` : ""}
                </Button>
              </div>
            )}
          </div>

          {isLoading ? (
            <div className="py-16 text-center text-sm text-[#74828D]">Loading inbox…</div>
          ) : documents.length === 0 &&
            !(showRejectedInList && sessionRejections.length > 0) ? (
            <div className="py-16 text-center">
              <p className="text-sm font-medium text-[#14212B]">{emptyCopy.title}</p>
              <p className="mt-1 text-xs text-[#42515D]">{emptyCopy.body}</p>
              <Button
                size="sm"
                className="mt-4"
                onClick={() => fileInputRef.current?.click()}
                disabled={uploader.busy}
              >
                Upload documents
              </Button>
            </div>
          ) : (
            <div>
              {showRejectedInList &&
                sessionRejections.map((r) => (
                  <InboxRejectedCard
                    key={r.id}
                    rejection={r}
                    onDismiss={onDismissRejection}
                  />
                ))}
              {documents.map((doc) => {
                const docSuggestions = suggestionsByDoc[doc.id] ?? [];
                return (
                <InboxReviewCard
                  key={doc.id}
                  document={doc}
                  suggestions={docSuggestions}
                  selected={selectedIds.has(doc.id)}
                  expanded={isDocSettled(doc) && (expandedIds?.has(doc.id) ?? false)}
                  reviewReady={isDocSettled(doc)}
                  aiSuggestionsAvailable={aiSuggestionsAvailable}
                  filingUnavailableReason={
                    aiSuggestionsAvailable ? undefined : filingReason
                  }
                  suggestionJobStatus={suggestionJobStatusForDoc(
                    inboxJobs,
                    doc.id,
                    docSuggestions.length,
                  )}
                  onRetrySuggestions={
                    aiSuggestionsAvailable
                      ? () => void reprocessSuggestions.mutateAsync(doc.id)
                      : undefined
                  }
                  retrySuggestionsBusy={
                    retryBatchBusy || reprocessSuggestions.isPending
                  }
                  jobs={inboxJobs}
                  onToggleExpand={() => toggleExpand(doc.id)}
                  onSelect={(checked) => {
                    setSelectedIds((prev) => {
                      const next = new Set(prev);
                      if (checked) next.add(doc.id);
                      else next.delete(doc.id);
                      return next;
                    });
                  }}
                  onPreview={() => setPreviewId(doc.id)}
                  onRetry={() =>
                    void retryPreflight.mutateAsync(doc.id).then(() => refetch())
                  }
                  onRemove={() => setRemoveIds([doc.id])}
                  acceptSuggestionsBusy={acceptAllBusy}
                  onAcceptAllSuggestions={
                    aiSuggestionsAvailable
                      ? () => void handleAcceptAllForDoc(doc.id)
                      : undefined
                  }
                />
                );
              })}
            </div>
          )}
        </div>
      </div>

      <InboxPreviewDialog
        documentIds={documentIds}
        activeId={previewId}
        onActiveIdChange={setPreviewId}
      />

      <Dialog open={Boolean(removeIds)} onOpenChange={(o) => !o && setRemoveIds(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Remove from queue?</DialogTitle>
            <DialogDescription>
              This removes{" "}
              {removeIds?.length === 1 ? "the document" : `${removeIds?.length} documents`} from
              the Inbox and deletes the uploaded file. This cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setRemoveIds(null)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={removeFromQueue.isPending}
              onClick={() => void confirmRemove()}
            >
              Remove
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <InboxToast
        message={resultMsg ?? toastMessage}
        onDismiss={() => {
          setResultMsg(null);
          onDismissToast();
        }}
      />
    </UploadDropzone>
  );
}
