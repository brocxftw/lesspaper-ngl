import { useEffect, useMemo, useState } from "react";
import { ChevronDown, Loader2, Send, Sparkles } from "lucide-react";
import { BrandMark } from "@/components/brand/BrandMark";
import { ApiError } from "@/lib/api/client";
import { useAICapabilities, useAIHealth, useAsk, useFolders } from "@/lib/api/hooks";
import type {
  AskRequest,
  AskResponse,
  AskScope,
  Citation,
  Document,
  Folder,
  SearchScopeSnapshot,
} from "@/lib/api/types";
import { Button } from "@/components/ui/Button";
import { Textarea } from "@/components/ui/Textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { CitationList } from "./CitationList";
import { AnswerBody } from "./MarkdownResponse";
import {
  summarizeScopeReadiness,
  type ScopeReadinessSummary,
} from "@/features/documents/scopeReadiness";
import { cn } from "@/lib/utils";

export type AIDrawerScopeKind =
  | "library"
  | "folder"
  | "folder_tree"
  | "documents"
  | "document"
  | "search";

export interface AIDrawerScope {
  kind: AIDrawerScopeKind;
  documentId?: string;
  documentIds?: string[];
  folderId?: string;
  search?: SearchScopeSnapshot;
  /** Documents used only for readiness preview (not sent if empty for library). */
  previewDocuments?: Document[];
  label?: string;
}

export interface AIChatPanelProps {
  /** When true, reset local ask state from initialScope (e.g. drawer/modal open). */
  active?: boolean;
  initialScope?: AIDrawerScope;
  onCitationClick: (citation: Citation) => void;
  /** Show scope kind/folder selectors. Default true. */
  showScopeSelector?: boolean;
  className?: string;
  /** Compact header for embedded layouts (e.g. preview modal). */
  title?: string;
  description?: string;
  /** Composer with in-field context pills and an inner Send control (Ask dock). */
  compactComposer?: boolean;
}

function scopeToRequest(
  scope: AIDrawerScope,
  question: string,
  confirmRemote: boolean,
): AskRequest {
  const base: AskRequest = {
    question,
    confirm_remote: confirmRemote,
    scope: scope.kind as AskScope,
  };
  switch (scope.kind) {
    case "document":
      return { ...base, document_id: scope.documentId };
    case "documents":
      return { ...base, document_ids: scope.documentIds };
    case "folder":
    case "folder_tree":
      return { ...base, folder_id: scope.folderId };
    case "search":
      return {
        ...base,
        search: scope.search,
        search_query: scope.search?.query,
      };
    default:
      return base;
  }
}

function defaultLabel(scope: AIDrawerScope): string {
  if (scope.label) return scope.label;
  switch (scope.kind) {
    case "library":
      return "Entire library";
    case "folder":
      return "Current folder";
    case "folder_tree":
      return "Folder & subfolders";
    case "documents":
      return `${scope.documentIds?.length ?? 0} selected`;
    case "document":
      return "Current document";
    case "search":
      return `Search: ${scope.search?.query ?? ""}`;
    default:
      return "Scope";
  }
}

function contextPillClass(active: boolean): string {
  return cn(
    "inline-flex max-w-[220px] items-center rounded-full border px-2 py-0.5 text-[11px] font-medium transition-colors",
    active
      ? "border-accent/40 bg-accent/15 text-accent"
      : "border-surface-border bg-surface-muted text-text-secondary hover:bg-surface-hover",
  );
}

function ScopeContextPills({
  scope,
  folders,
  onChange,
}: {
  scope: AIDrawerScope;
  folders: Folder[];
  onChange: (next: AIDrawerScope) => void;
}) {
  const normalFolders = folders.filter((folder) => folder.kind === "normal");
  const selectedFolder =
    scope.kind === "folder" || scope.kind === "folder_tree"
      ? normalFolders.find((folder) => folder.id === scope.folderId)
      : undefined;
  const selectedLabel = selectedFolder?.path_cache
    ?? (scope.kind === "library" ? "Library" : scope.label ?? "Library");

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(contextPillClass(true), "gap-1 pr-1.5")}
          aria-label="Select ask context"
        >
          <span className="truncate">{selectedLabel}</span>
          <ChevronDown className="h-3 w-3 shrink-0 opacity-70" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        className="flex w-[min(360px,calc(100vw-4rem))] flex-wrap gap-1.5 p-2"
      >
        <DropdownMenuItem
          className={contextPillClass(scope.kind === "library")}
          onSelect={() => onChange({ kind: "library" })}
        >
          Library
        </DropdownMenuItem>
        {normalFolders.map((folder) => (
          <DropdownMenuItem
            key={folder.id}
            title={folder.path_cache}
            className={contextPillClass(
              Boolean(selectedFolder && selectedFolder.id === folder.id),
            )}
            onSelect={() =>
              onChange({
                kind: "folder_tree",
                folderId: folder.id,
                label: folder.path_cache,
              })
            }
          >
            <span className="truncate">{folder.path_cache}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AIChatPanel({
  active = true,
  initialScope,
  onCitationClick,
  showScopeSelector = true,
  className,
  title = "Ask AI",
  description = "Single-turn answers with citations from the selected scope.",
  compactComposer = false,
}: AIChatPanelProps) {
  const [question, setQuestion] = useState("");
  const [scope, setScope] = useState<AIDrawerScope>(
    initialScope ?? { kind: "library" },
  );
  const [response, setResponse] = useState<AskResponse | null>(null);
  const [pendingRemote, setPendingRemote] = useState<AskRequest | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ask = useAsk();
  const { data: policy } = useAICapabilities();
  const { data: aiHealth } = useAIHealth();
  const chatAvailable = aiHealth?.chat.status === "available";
  const { data: folders = [] } = useFolders();

  const scopeIdentity = [
    initialScope?.kind,
    initialScope?.documentId,
    initialScope?.folderId,
    initialScope?.documentIds?.join(","),
    initialScope?.search?.query,
    initialScope?.label,
  ].join("|");

  useEffect(() => {
    if (active && initialScope) {
      setScope(initialScope);
      setResponse(null);
      setError(null);
      setPendingRemote(null);
      setQuestion("");
    }
    // Reset when the panel becomes active or the logical scope identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- intentional stable identity
  }, [active, scopeIdentity]);

  const readiness: ScopeReadinessSummary | null = useMemo(() => {
    const docs = scope.previewDocuments ?? [];
    if (docs.length === 0) return null;
    return summarizeScopeReadiness(docs, defaultLabel(scope));
  }, [scope]);

  const submit = async (confirmRemote = false) => {
    if (!question.trim()) return;
    setError(null);
    const body = scopeToRequest(scope, question.trim(), confirmRemote);
    if (
      (scope.kind === "folder" || scope.kind === "folder_tree") &&
      !body.folder_id
    ) {
      setError("Select a folder for this scope.");
      return;
    }
    if (scope.kind === "documents" && !body.document_ids?.length) {
      setError("Select at least one document.");
      return;
    }
    if (scope.kind === "document" && !body.document_id) {
      setError("Open a document to ask about it.");
      return;
    }
    if (scope.kind === "search" && !body.search?.query && !body.search_query) {
      setError("Run a search first to ask about results.");
      return;
    }

    try {
      const result = await ask.mutateAsync(body);
      setPendingRemote(null);
      setResponse(result);
    } catch (err) {
      if (err instanceof ApiError && err.isForbidden) {
        setPendingRemote(body);
        setError(
          err.message ||
            "This provider is remote. Confirm to send the question outside your host.",
        );
        return;
      }
      setError(
        err instanceof Error
          ? err.message
          : "Unable to get an answer. Check AI providers in Settings.",
      );
      setResponse(null);
    }
  };

  const scopeKind = scope.kind;

  return (
    <div className={cn("flex min-h-0 flex-1 flex-col", className)}>
      <div className="border-b border-surface-border px-4 py-3 pr-10">
        <div className="flex items-center gap-2 text-sm font-semibold text-text-primary">
          <Sparkles className="h-4 w-4 text-text-muted" />
          {title}
        </div>
        {description && (
          <p className="mt-1 text-xs text-text-secondary">{description}</p>
        )}
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        {showScopeSelector && !compactComposer ? (
          <div className="space-y-3 border-b border-surface-border px-4 py-3">
            <div>
              <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-text-muted">
                Scope
              </p>
              <Select
                value={scopeKind}
                onValueChange={(v) => {
                  const kind = v as AIDrawerScopeKind;
                  if (kind === "library") setScope({ kind: "library" });
                  else if (kind === "folder" || kind === "folder_tree") {
                    setScope({
                      kind,
                      folderId: scope.folderId ?? initialScope?.folderId,
                    });
                  } else if (kind === "search") {
                    setScope({
                      kind: "search",
                      search: scope.search ?? initialScope?.search,
                      previewDocuments:
                        scope.previewDocuments ?? initialScope?.previewDocuments,
                    });
                  } else if (kind === "documents") {
                    setScope({
                      kind: "documents",
                      documentIds:
                        scope.documentIds ?? initialScope?.documentIds ?? [],
                      previewDocuments:
                        scope.previewDocuments ?? initialScope?.previewDocuments,
                    });
                  } else {
                    setScope({
                      kind: "document",
                      documentId: scope.documentId ?? initialScope?.documentId,
                      previewDocuments:
                        scope.previewDocuments ?? initialScope?.previewDocuments,
                    });
                  }
                  setResponse(null);
                }}
              >
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="library">Entire library</SelectItem>
                  <SelectItem value="folder">Single folder</SelectItem>
                  <SelectItem value="folder_tree">Folder & subfolders</SelectItem>
                  <SelectItem value="documents">Selected documents</SelectItem>
                  <SelectItem value="document">Current document</SelectItem>
                  <SelectItem value="search">Search results</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {(scopeKind === "folder" || scopeKind === "folder_tree") && (
              <Select
                value={scope.folderId ?? ""}
                onValueChange={(folderId) =>
                  setScope((s) => ({ ...s, folderId }))
                }
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Select folder" />
                </SelectTrigger>
                <SelectContent>
                  {folders
                    .filter((f) => f.kind === "normal")
                    .map((f) => (
                      <SelectItem key={f.id} value={f.id}>
                        {f.path_cache}
                      </SelectItem>
                    ))}
                </SelectContent>
              </Select>
            )}

            <div className="rounded-md bg-surface-muted px-2.5 py-2 text-[12px] text-text-secondary">
              <p className="font-medium text-text-primary">{defaultLabel(scope)}</p>
              {scopeKind === "search" && scope.search && (
                <p className="mt-0.5 text-[11px] text-text-muted">
                  {scope.search.mode ?? "hybrid"}
                  {scope.search.folder_id ? " · folder scoped" : ""}
                  {scope.search.tag_ids?.length
                    ? ` · ${scope.search.tag_ids.length} tag(s)`
                    : ""}
                </p>
              )}
              {readiness ? (
                <p className="mt-1 text-[11px] text-text-muted">
                  {readiness.askReady}/{readiness.total} ready for Ask
                  {readiness.semanticReady
                    ? ` · ${readiness.semanticReady} semantic`
                    : ""}
                  {readiness.unavailable
                    ? ` · ${readiness.unavailable} not indexed`
                    : ""}
                </p>
              ) : (
                <p className="mt-1 text-[11px] text-text-muted">
                  Scope readiness is estimated from visible documents when available.
                </p>
              )}
            </div>
          </div>
        ) : compactComposer ? null : (
          <div className="border-b border-surface-border px-4 py-2">
            <div className="rounded-md bg-surface-muted px-2.5 py-2 text-[12px] text-text-secondary">
              <p className="font-medium text-text-primary">{defaultLabel(scope)}</p>
              {readiness ? (
                <p className="mt-1 text-[11px] text-text-muted">
                  {readiness.askReady}/{readiness.total} ready for Ask
                  {readiness.semanticReady
                    ? ` · ${readiness.semanticReady} semantic`
                    : ""}
                </p>
              ) : null}
            </div>
          </div>
        )}

        <div className="min-h-0 flex-1 overflow-auto px-4 py-3 scrollbar-thin">
          {ask.isPending ? (
            <div className="rounded-xl border border-surface-border bg-surface p-3.5">
              <div className="mb-2 flex items-center gap-2 text-xs text-text-muted">
                <BrandMark variant="on-light" size={14} />
                lesspaper-ngl
              </div>
              <p
                className="flex items-center gap-2 text-sm text-text-secondary"
                aria-live="polite"
              >
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                Generating answer…
              </p>
            </div>
          ) : response ? (
            <div className="space-y-4">
              <div className="rounded-md border border-surface-border bg-surface p-3">
                <AnswerBody
                  content={response.answer}
                  citations={response.citations}
                  onActivate={onCitationClick}
                  className="text-[13px] leading-relaxed text-text-primary"
                />
                {response.insufficient_evidence && (
                  <p className="mt-2 text-xs text-warning">
                    Insufficient evidence found in the selected scope.
                  </p>
                )}
                {(response.provider || response.model) && (
                  <p className="mt-2 text-[11px] text-text-muted">
                    {response.provider}
                    {response.model && ` · ${response.model}`}
                    {response.is_local ? " · local" : " · remote"}
                  </p>
                )}
              </div>
              <CitationList
                citations={response.citations}
                onOpen={onCitationClick}
              />
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setResponse(null);
                  setQuestion("");
                }}
              >
                Ask another question
              </Button>
            </div>
          ) : (
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <Sparkles className="mb-3 h-8 w-8 text-text-muted/40" />
              <p className="text-sm text-text-secondary">
                {chatAvailable
                  ? "Ask a question about this scope"
                  : "Chat AI is currently unavailable"}
              </p>
              <p className="mt-1 max-w-xs text-xs text-text-muted">
                {chatAvailable
                  ? "Answers cite passages you can open in the document viewer."
                  : aiHealth?.chat.error ||
                    "Configure a chat model in Settings, or try again when the provider is online."}
              </p>
            </div>
          )}
        </div>

        <form
          className="space-y-2 border-t border-surface-border p-4"
          onSubmit={(e) => {
            e.preventDefault();
            void submit(false);
          }}
        >
          {compactComposer ? (
            <div className="relative rounded-md border border-surface-border bg-surface focus-within:ring-2 focus-within:ring-focus focus-within:ring-offset-1">
              <div className="flex items-center px-2 pt-2">
                <ScopeContextPills
                  scope={scope}
                  folders={folders}
                  onChange={(next) => {
                    setScope(next);
                    setResponse(null);
                  }}
                />
              </div>
              <Textarea
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder={
                  chatAvailable
                    ? "What would you like to know?"
                    : "Chat unavailable"
                }
                className="min-h-[72px] resize-none border-0 bg-transparent pr-12 shadow-none focus-visible:ring-0 focus-visible:ring-offset-0"
                disabled={ask.isPending || !chatAvailable}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void submit(false);
                  }
                }}
              />
              <Button
                type="submit"
                size="icon"
                className="absolute bottom-2 right-2 h-8 w-8 rounded-lg"
                disabled={!chatAvailable || !question.trim() || ask.isPending}
                aria-label={ask.isPending ? "Generating answer" : "Send"}
              >
                {ask.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Send className="h-3.5 w-3.5" />
                )}
              </Button>
            </div>
          ) : (
            <Textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={
                chatAvailable
                  ? "What would you like to know?"
                  : "Chat unavailable"
              }
              className="min-h-[72px] resize-none"
              disabled={ask.isPending || !chatAvailable}
            />
          )}
          {error && <p className="text-xs text-danger">{error}</p>}
          {pendingRemote && policy?.warn_before_remote_chat && (
            <Button
              type="button"
              variant="secondary"
              className="w-full"
              disabled={ask.isPending}
              onClick={() => void submit(true)}
            >
              Confirm remote AI and ask
            </Button>
          )}
          {!compactComposer && (
            <>
              <Button
                type="submit"
                className="w-full gap-1"
                disabled={!chatAvailable || !question.trim() || ask.isPending}
              >
                <Send className="h-3.5 w-3.5" />
                {ask.isPending ? "Thinking…" : "Ask"}
              </Button>
              <p className="text-[11px] text-text-muted">
                AI responses can be inaccurate. Verify important information.
              </p>
            </>
          )}
        </form>
      </div>
    </div>
  );
}
