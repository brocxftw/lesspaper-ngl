import { useState } from "react";
import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import { Link } from "react-router-dom";
import { cn, formatDate } from "@/lib/utils";
import type { SearchHit, SearchMatch, SearchResponse } from "@/lib/api/types";
import { TagList } from "@/components/tags/TagList";
import { RetrievalReadinessBadge } from "@/features/documents/RetrievalReadinessBadge";
import { sanitizeSearchSnippet } from "./sanitizeSnippet";

interface EvidenceSearchResultsProps {
  response: SearchResponse | undefined;
  isLoading?: boolean;
  onOpen: (documentId: string, page?: number | null) => void;
  selectedIds?: Set<string>;
  onSelect?: (ids: Set<string>) => void;
  onAskAboutResults?: () => void;
  askHref?: string;
  emptyMessage?: string;
}

export function EvidenceSearchResults({
  response,
  isLoading,
  onOpen,
  onAskAboutResults,
  askHref,
  emptyMessage = "No results found",
}: EvidenceSearchResultsProps) {
  if (isLoading) {
    return <p className="p-6 text-sm text-text-muted">Searching…</p>;
  }

  if (!response) return null;

  const docTotal = response.document_total ?? response.total;
  const matchTotal = response.match_total ?? response.items.length;
  const coverage = response.semantic_coverage;
  const items = response.items;

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 text-center">
        <FileText className="mb-3 h-10 w-10 text-text-muted/40" />
        <p className="text-sm text-text-secondary">{emptyMessage}</p>
        <p className="mt-1 text-xs text-text-muted">Try different keywords or filters</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 px-1" aria-live="polite">
        <p className="text-xs text-text-muted">
          {docTotal} document{docTotal !== 1 ? "s" : ""}
          {matchTotal !== docTotal ? ` · ${matchTotal} matches` : ""}
          {response.effective_mode && response.effective_mode !== response.mode
            ? ` · fell back to ${response.effective_mode}`
            : ` · ${response.effective_mode ?? response.mode}`}
        </p>
        {coverage?.partial && (
          <span className="rounded bg-warning/15 px-1.5 py-0.5 text-[11px] text-warning">
            Partial semantic coverage ({coverage.embedded_documents}/
            {coverage.searchable_documents} embedded)
          </span>
        )}
        {!response.semantic_available && (
          <span className="text-[11px] text-text-muted">
            Semantic unavailable — keyword/hybrid fallback
          </span>
        )}
        {(onAskAboutResults || askHref) && (
          onAskAboutResults ? (
            <button
              type="button"
              onClick={onAskAboutResults}
              className="ml-auto text-xs font-medium text-accent hover:underline"
            >
              Ask AI about these results
            </button>
          ) : (
            <Link
              to={askHref!}
              className="ml-auto text-xs font-medium text-accent hover:underline"
            >
              Ask AI about these results
            </Link>
          )
        )}
      </div>

      <ul className="space-y-2">
        {items.map((hit) => (
          <EvidenceResultCard key={hit.document.id} hit={hit} onOpen={onOpen} />
        ))}
      </ul>
    </div>
  );
}

function EvidenceResultCard({
  hit,
  onOpen,
}: {
  hit: SearchHit;
  onOpen: (documentId: string, page?: number | null) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const matches = hit.matches?.length ? hit.matches : [toLegacyMatch(hit)];

  return (
    <li className="rounded-md border border-surface-border bg-surface">
      <button
        type="button"
        onClick={() => onOpen(hit.document.id, hit.page_number)}
        className="flex w-full items-start gap-3 p-3 text-left hover:bg-surface-hover"
      >
        <FileText className="mt-0.5 h-4 w-4 shrink-0 text-text-muted" />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate font-medium text-text-primary">
              {hit.document.title}
            </span>
            <RetrievalReadinessBadge document={hit.document} />
            <span className="ml-auto shrink-0 text-xs text-text-muted">
              {formatDate(hit.document.added_date)}
            </span>
          </div>
          <p className="mt-0.5 truncate text-xs text-text-muted">
            {hit.document.folder_path}
          </p>
          {hit.snippet && (
            <p
              className="mt-2 line-clamp-2 text-[13px] text-text-secondary"
              dangerouslySetInnerHTML={{ __html: sanitizeSearchSnippet(hit.snippet) }}
            />
          )}
          <TagList tags={hit.document.tags} max={3} className="mt-2" />
        </div>
      </button>

      {matches.length > 0 && (
        <div className="border-t border-surface-border px-3 py-2">
          <button
            type="button"
            className="inline-flex items-center gap-1 text-[11px] font-medium text-text-secondary hover:text-text-primary"
            onClick={() => setExpanded((v) => !v)}
            aria-expanded={expanded}
          >
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
            {matches.length} evidence match{matches.length !== 1 ? "es" : ""}
          </button>
          {expanded && (
            <ul className="mt-2 space-y-2">
              {matches.map((m, i) => (
                <li key={`${m.kind}-${m.page_number}-${m.chunk_id}-${i}`}>
                  <button
                    type="button"
                    className={cn(
                      "w-full rounded border border-surface-border bg-surface-muted/50 px-2.5 py-2 text-left",
                      "hover:border-accent/30 hover:bg-surface-hover",
                    )}
                    onClick={() => onOpen(hit.document.id, m.page_number)}
                  >
                    <div className="flex items-center gap-2 text-[11px] text-text-muted">
                      <span className="uppercase tracking-wide">{m.kind}</span>
                      {m.page_number != null && <span>p.{m.page_number}</span>}
                    </div>
                    {m.snippet && (
                      <p
                        className="mt-1 line-clamp-3 text-[12px] text-text-secondary"
                        dangerouslySetInnerHTML={{
                          __html: sanitizeSearchSnippet(m.snippet),
                        }}
                      />
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </li>
  );
}

function toLegacyMatch(hit: SearchHit): SearchMatch {
  return {
    kind: hit.chunk_id ? "chunk" : hit.page_number ? "page" : "document",
    score: hit.score,
    snippet: hit.snippet,
    page_number: hit.page_number,
    chunk_id: hit.chunk_id,
  };
}
