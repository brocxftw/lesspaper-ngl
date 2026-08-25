import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useBulkAction,
  useDocuments,
  useFolders,
  useSearch,
  useTags,
} from "@/lib/api/hooks";
import type { BulkAction, Citation } from "@/lib/api/types";
import { useDocumentUploader } from "@/lib/api/upload";
import type { UploadEntry } from "@/lib/uploadTree";
import { usePersistedState } from "@/lib/usePersistedState";
import { UploadDropzone } from "@/components/documents/UploadDropzone";
import { UploadStatusBar } from "@/components/documents/UploadStatusBar";
import { DocumentTable } from "@/components/documents/DocumentTable";
import { Breadcrumbs } from "@/components/documents/Breadcrumbs";
import { EvidenceSearchResults } from "@/components/search/EvidenceSearchResults";
import {
  AIChatDrawer,
  type AIDrawerScope,
} from "@/components/ask/AIChatDrawer";
import { DocumentExplorerSidebar } from "./DocumentExplorerSidebar";
import { DocumentsHeader } from "./DocumentsHeader";
import { RecentDocuments } from "./RecentDocuments";
import {
  DocumentBulkToolbar,
  DocumentResultsToolbar,
  type BulkActionOptions,
} from "./DocumentBulkToolbar";
import { DocumentGrid } from "./DocumentGrid";
import { DocumentViewerModal } from "./DocumentViewerModal";
import { MobileLibraryExplorer } from "./MobileLibraryExplorer";
import { DocumentViewTabs } from "./DocumentViewTabs";
import { Button } from "@/components/ui/Button";
import { Sparkles } from "lucide-react";
import {
  DOCUMENTS_LAYOUT_PREF_KEY,
  DOCUMENTS_LAYOUT_PREF_KEY_LEGACY,
  type DocumentsLayoutMode,
} from "./documentSelection";
import {
  libraryStateToSearchSnapshot,
  useDocumentsLibraryState,
} from "./useDocumentsLibraryState";
import { documentsNeedProcessingPoll } from "./retrievalReadiness";

function emptyMessageForView(
  view: string,
  hasFolder: boolean,
): string {
  if (view === "unprocessed") return "No unprocessed documents";
  if (view === "recent") return "No recently added documents";
  if (hasFolder) return "No documents in this folder";
  return "No documents yet";
}

export function DocumentsPage() {
  const navigate = useNavigate();
  const {
    state,
    patch,
    openDocument,
    closeDocument,
    setViewerPage,
    listParams,
    isEvidenceSearch,
    evidenceRequest,
  } = useDocumentsLibraryState();

  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [aiOpen, setAiOpen] = useState(false);
  const [aiScope, setAiScope] = useState<AIDrawerScope>({ kind: "library" });
  const [layoutModeRaw, setLayoutMode] = usePersistedState<DocumentsLayoutMode>(
    DOCUMENTS_LAYOUT_PREF_KEY,
    "list",
    DOCUMENTS_LAYOUT_PREF_KEY_LEGACY,
  );
  const layoutMode: DocumentsLayoutMode =
    layoutModeRaw === "grid" ? "grid" : "list";

  const { data: folders = [] } = useFolders();
  const { data: tags = [] } = useTags();

  const { data: docList, isLoading, refetch, isFetching } = useDocuments(listParams, {
    enabled: !isEvidenceSearch,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      return documentsNeedProcessingPoll(items) ? 3_000 : false;
    },
  });

  const {
    data: searchResponse,
    isFetching: isSearching,
    isLoading: isSearchLoading,
  } = useSearch(evidenceRequest, isEvidenceSearch);

  const { data: recentList } = useDocuments(
    {
      inbox: false,
      sort: "added_date",
      order: "desc",
      page: 1,
      page_size: 5,
      folder_id: state.folderId,
      include_descendants: !!state.folderId,
    },
    { enabled: state.view !== "unprocessed" && !isEvidenceSearch },
  );

  const bulkAction = useBulkAction();
  const uploader = useDocumentUploader();

  const browseDocuments = docList?.items ?? [];
  const searchDocuments = searchResponse?.items.map((h) => h.document) ?? [];
  const documents = isEvidenceSearch ? searchDocuments : browseDocuments;

  const folderName = useMemo(() => {
    if (!state.folderId) return undefined;
    return folders.find((f) => f.id === state.folderId)?.name;
  }, [folders, state.folderId]);

  const filterChips = useMemo(() => {
    const chips: Array<{ id: string; label: string; onClear: () => void }> = [];
    if (state.q.trim()) {
      chips.push({
        id: "q",
        label: `Search: ${state.q.trim()}`,
        onClear: () => patch({ q: "" }),
      });
    }
    for (const tagId of state.tagIds) {
      const tag = tags.find((t) => t.id === tagId);
      chips.push({
        id: `tag-${tagId}`,
        label: tag ? `Tag: ${tag.name}` : "Tag",
        onClear: () =>
          patch({ tagIds: state.tagIds.filter((id) => id !== tagId) }),
      });
    }
    if (state.folderId) {
      chips.push({
        id: "folder",
        label: folderName ? `Folder: ${folderName}` : "Folder",
        onClear: () => patch({ folderId: undefined }),
      });
    }
    return chips;
  }, [state.q, state.tagIds, state.folderId, tags, folderName, patch]);

  const handleEntries = useCallback(
    async (entries: UploadEntry[]) => {
      await uploader.uploadEntries(entries);
      navigate("/inbox?view=work");
    },
    [uploader, navigate],
  );

  const handleBulkAction = async (action: BulkAction, options?: BulkActionOptions) => {
    if (selectedIds.size === 0) return;
    if (action === "move" && !options?.folder_id) return;
    if (action === "tag" && !options?.tag_ids?.length) return;
    await bulkAction.mutateAsync({
      document_ids: Array.from(selectedIds),
      action,
      folder_id: options?.folder_id,
      tag_ids: options?.tag_ids,
    });
    setSelectedIds(new Set());
    void refetch();
  };

  const handleDropDocuments = useCallback(
    async (folderId: string, documentIds: string[]) => {
      if (documentIds.length === 0) return;
      await bulkAction.mutateAsync({
        document_ids: documentIds,
        action: "move",
        folder_id: folderId,
      });
      setSelectedIds(new Set());
      void refetch();
    },
    [bulkAction, refetch],
  );

  const handleTagToggle = (tagId: string) => {
    const next = state.tagIds.includes(tagId)
      ? state.tagIds.filter((id) => id !== tagId)
      : [...state.tagIds, tagId];
    patch({ tagIds: next });
  };

  useEffect(() => {
    setSelectedIds(new Set());
  }, [state.view, state.folderId, state.q, state.searchMode, state.tagIds.join(","), state.page]);

  const showRecentCards =
    !isEvidenceSearch &&
    state.view !== "unprocessed" &&
    state.tagIds.length === 0 &&
    state.page === 1;

  const evidenceTotal = searchResponse?.document_total ?? searchResponse?.total ?? 0;

  const openAsk = useCallback(
    (scope: AIDrawerScope) => {
      setAiScope(scope);
      setAiOpen(true);
    },
    [],
  );

  const handleCitation = useCallback(
    (citation: Citation) => {
      openDocument(
        citation.document_id,
        citation.page_number ?? undefined,
      );
    },
    [openDocument],
  );

  return (
    <UploadDropzone
      onEntries={(entries) => void handleEntries(entries)}
      className="h-full"
      disabled={uploader.busy}
    >
      <div className="flex h-full min-h-0">
        <DocumentExplorerSidebar
          folders={folders}
          tags={tags}
          view={state.view}
          folderId={state.folderId}
          tagIds={state.tagIds}
          onViewChange={(view) => patch({ view, folderId: undefined })}
          onFolderSelect={(folderId) =>
            patch({ folderId, view: folderId ? "all" : state.view })
          }
          onTagToggle={handleTagToggle}
          onDropDocuments={(folderId, ids) => void handleDropDocuments(folderId, ids)}
          className="hidden md:flex"
        />

        <div className="flex min-w-0 flex-1 flex-col bg-surface">
          <DocumentsHeader
            view={state.view}
            onViewChange={(view) => patch({ view })}
          />

          <div className="border-b border-surface-border bg-surface px-4 py-4 md:hidden">
            <h1 className="mb-3 text-xl font-bold text-text-primary">Library</h1>
            <MobileLibraryExplorer
              folders={folders}
              tags={tags}
              view={state.view}
              folderId={state.folderId}
              tagIds={state.tagIds}
              total={docList?.total ?? 0}
              onViewChange={(view) => patch({ view, folderId: undefined })}
              onFolderSelect={(folderId) => patch({ folderId, view: folderId ? "all" : state.view })}
              onTagToggle={handleTagToggle}
            />
            <DocumentViewTabs view={state.view} onChange={(view) => patch({ view, folderId: undefined })} className="mt-4 grid grid-cols-3 gap-1 rounded-[10px] border border-surface-border p-1 [&>button]:min-h-10 [&>button]:justify-center" />
          </div>

          <UploadStatusBar
            busy={uploader.busy}
            progress={uploader.progress}
            summary={uploader.lastSummary}
            onDismiss={uploader.clearSummary}
          />

          {state.folderId && (
            <div className="border-b border-surface-border px-4 py-2">
              <Breadcrumbs
                folderId={state.folderId}
                folders={folders}
                onNavigate={(folderId) =>
                  patch({ folderId, view: folderId ? "all" : state.view })
                }
              />
            </div>
          )}

          <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto px-4 py-3">
            {(isFetching || isSearching) && !(isLoading || isSearchLoading) && (
              <div className="flex justify-end">
                <span className="text-[11px] text-text-muted">Updating…</span>
              </div>
            )}

            {showRecentCards && (
              <RecentDocuments
                documents={recentList?.items ?? []}
                onOpen={(id) => openDocument(id)}
              />
            )}

            {!isEvidenceSearch && (
              <DocumentBulkToolbar
                selectedCount={selectedIds.size}
                onClear={() => setSelectedIds(new Set())}
                onBulkAction={handleBulkAction}
                onAsk={() =>
                  openAsk({
                    kind: "documents",
                    documentIds: Array.from(selectedIds),
                    previewDocuments: documents.filter((d) => selectedIds.has(d.id)),
                  })
                }
                isPending={bulkAction.isPending}
                folders={folders}
                tags={tags}
              />
            )}

            {!isEvidenceSearch && (
              <DocumentResultsToolbar
                total={docList?.total ?? 0}
                page={state.page}
                pageSize={state.pageSize}
                sort={state.sort}
                order={state.order}
                onSortChange={(sort, order) => patch({ sort, order })}
                layoutMode={layoutMode}
                onLayoutModeChange={setLayoutMode}
                filterChips={filterChips}
              />
            )}

            {isEvidenceSearch && filterChips.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {filterChips.map((chip) => (
                  <button
                    key={chip.id}
                    type="button"
                    onClick={chip.onClear}
                    className="inline-flex items-center gap-1 rounded-md bg-surface-muted px-2 py-0.5 text-[11px] text-text-secondary hover:bg-surface-hover"
                  >
                    {chip.label}
                    <span aria-hidden>×</span>
                  </button>
                ))}
              </div>
            )}

            <div className="flex min-h-[320px] flex-1 flex-col overflow-hidden rounded-md border border-surface-border">
              {isEvidenceSearch ? (
                <div className="flex-1 overflow-auto p-3 scrollbar-thin">
                  <EvidenceSearchResults
                    response={searchResponse}
                    isLoading={isSearchLoading}
                    onOpen={(id, page) => openDocument(id, page ?? undefined)}
                    onAskAboutResults={() => {
                      const snapshot = libraryStateToSearchSnapshot(state);
                      if (!snapshot) return;
                      openAsk({
                        kind: "search",
                        search: snapshot,
                        previewDocuments: searchDocuments,
                      });
                    }}
                    emptyMessage="No evidence matches this search"
                  />
                  {evidenceTotal > state.pageSize && (
                    <div className="mt-3 flex items-center justify-between text-xs text-text-muted">
                      <span>
                        Page {state.page} of{" "}
                        {Math.max(1, Math.ceil(evidenceTotal / state.pageSize))}
                      </span>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          className="hover:text-text-primary disabled:opacity-40"
                          disabled={state.page <= 1}
                          onClick={() => patch({ page: state.page - 1 })}
                        >
                          Previous
                        </button>
                        <button
                          type="button"
                          className="hover:text-text-primary disabled:opacity-40"
                          disabled={
                            state.page >= Math.ceil(evidenceTotal / state.pageSize)
                          }
                          onClick={() => patch({ page: state.page + 1 })}
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              ) : layoutMode === "grid" ? (
                <DocumentGrid
                  documents={browseDocuments}
                  selectedIds={selectedIds}
                  activeId={state.docId}
                  folders={folders}
                  tags={tags}
                  onSelect={setSelectedIds}
                  onActiveChange={(id) => openDocument(id)}
                  onActionComplete={() => void refetch()}
                  isLoading={isLoading}
                  emptyMessage={emptyMessageForView(state.view, !!state.folderId)}
                  page={state.page}
                  pageSize={state.pageSize}
                  total={docList?.total}
                  onPageChange={(page) => patch({ page })}
                />
              ) : (
                <DocumentTable
                  documents={browseDocuments}
                  selectedIds={selectedIds}
                  activeId={state.docId}
                  folders={folders}
                  tags={tags}
                  onSelect={setSelectedIds}
                  onActiveChange={(id) => openDocument(id)}
                  onActionComplete={() => void refetch()}
                  isLoading={isLoading}
                  emptyMessage={emptyMessageForView(state.view, !!state.folderId)}
                  page={state.page}
                  pageSize={state.pageSize}
                  total={docList?.total}
                  onPageChange={(page) => patch({ page })}
                />
              )}
            </div>
          </div>
          {!isEvidenceSearch && selectedIds.size === 0 && (
            <Button
              type="button"
              className="fixed right-5 bottom-5 z-30 h-12 rounded-full px-4 shadow-lg md:hidden"
              onClick={() => openAsk(state.folderId ? { kind: "folder_tree", folderId: state.folderId } : { kind: "library" })}
            >
              <Sparkles className="h-4 w-4" /> Ask AI
            </Button>
          )}
        </div>
      </div>

      <DocumentViewerModal
        activeId={state.docId ?? null}
        page={state.viewerPage}
        folders={folders}
        onActiveIdChange={(id) => {
          if (id) openDocument(id);
          else closeDocument();
        }}
        onPageChange={setViewerPage}
        onNavigateToFolder={(folderId) => {
          closeDocument();
          patch({ folderId, view: "all" });
        }}
        onTrashed={() => {
          closeDocument();
          void refetch();
        }}
      />

      <AIChatDrawer
        open={aiOpen}
        onOpenChange={setAiOpen}
        initialScope={aiScope}
        onCitationClick={handleCitation}
      />
    </UploadDropzone>
  );
}
