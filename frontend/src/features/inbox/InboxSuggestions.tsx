import { Check, Sparkles, X } from "lucide-react";
import type { Suggestion } from "@/lib/api/types";
import {
  useAcceptSuggestion,
  useDocumentSuggestions,
  useRejectSuggestion,
} from "@/lib/api/hooks";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

/** Normalize tags suggestion value into individual display names. */
export function tagNamesFromSuggestion(s: Suggestion): string[] {
  const raw = s.value.tag_names;
  if (!Array.isArray(raw)) return [];
  const names: string[] = [];
  for (const entry of raw) {
    if (typeof entry !== "string") continue;
    // Split accidental comma-joined single values into tiles.
    for (const part of entry.split(",")) {
      const name = part.trim();
      if (name) names.push(name);
    }
  }
  return names;
}

export function formatSuggestionLabel(s: Suggestion): string {
  const v = s.value;
  if (s.field === "folder") {
    const path = typeof v.path === "string" ? v.path : "—";
    const create = v.create === true;
    return create ? `Create folder: ${path}` : `Move to: ${path}`;
  }
  if (s.field === "tags") {
    const names = tagNamesFromSuggestion(s);
    return names.length ? names.join(", ") : "Tags";
  }
  if (s.field === "title" && typeof v.title === "string") {
    return v.title;
  }
  if (s.field === "document_type" && typeof v.name === "string") {
    return v.name;
  }
  if (s.field === "correspondent" && typeof v.name === "string") {
    return v.name;
  }
  return s.field;
}

interface SuggestionChipProps {
  suggestion: Suggestion;
  stopPropagation?: boolean;
  className?: string;
  compact?: boolean;
}

function SuggestionActions({
  suggestionId,
  field,
  busy,
  onAccept,
  onReject,
}: {
  suggestionId: string;
  field: string;
  busy: boolean;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
}) {
  return (
    <div className="flex shrink-0 gap-0.5">
      <Button
        type="button"
        size="icon"
        variant="ghost"
        className="h-5 w-5 text-accent hover:bg-accent-muted"
        disabled={busy}
        aria-label={`Accept ${field}`}
        onClick={() => onAccept(suggestionId)}
      >
        <Check className="h-3 w-3" />
      </Button>
      <Button
        type="button"
        size="icon"
        variant="ghost"
        className="h-5 w-5 text-[#5D6B76] hover:bg-[#E8EEF1]"
        disabled={busy}
        aria-label={`Reject ${field}`}
        onClick={() => onReject(suggestionId)}
      >
        <X className="h-3 w-3" />
      </Button>
    </div>
  );
}

/** Single pending AI suggestion with accept / reject. */
export function SuggestionChip({
  suggestion,
  stopPropagation,
  className,
  compact,
}: SuggestionChipProps) {
  const accept = useAcceptSuggestion();
  const reject = useRejectSuggestion();
  const busy = accept.isPending || reject.isPending;

  return (
    <div
      className={cn(
        "flex items-start gap-1 rounded-md border border-dashed border-[#C9D2D8] bg-[#F1F4F6] px-1.5 py-1",
        className,
      )}
      onClick={(e) => {
        if (stopPropagation) e.stopPropagation();
      }}
    >
      <Sparkles
        className="mt-0.5 h-3 w-3 shrink-0 text-[#5D6B76]"
        strokeWidth={1.75}
        aria-hidden
      />
      <p
        className={cn(
          "min-w-0 flex-1 leading-snug text-[#24333D]",
          compact ? "text-[11px]" : "text-xs",
        )}
        title={formatSuggestionLabel(suggestion)}
      >
        {formatSuggestionLabel(suggestion)}
      </p>
      <SuggestionActions
        suggestionId={suggestion.id}
        field={suggestion.field}
        busy={busy}
        onAccept={(id) => accept.mutate(id)}
        onReject={(id) => reject.mutate(id)}
      />
    </div>
  );
}

interface TagSuggestionTilesProps {
  suggestions: Suggestion[];
  stopPropagation?: boolean;
  className?: string;
}

/**
 * Tag suggestions as individual tiles with per-suggestion accept/reject.
 * Legacy multi-name rows keep shared actions.
 */
export function TagSuggestionTiles({
  suggestions,
  stopPropagation,
  className,
}: TagSuggestionTilesProps) {
  if (suggestions.length === 0) return null;

  const hasLegacyBundle = suggestions.some(
    (s) => tagNamesFromSuggestion(s).length > 1,
  );

  if (!hasLegacyBundle) {
    return (
      <div
        className={cn("flex flex-wrap items-center gap-1.5", className)}
        onClick={(e) => {
          if (stopPropagation) e.stopPropagation();
        }}
      >
        {suggestions.map((s) => (
          <SuggestionChip key={s.id} suggestion={s} stopPropagation={stopPropagation} />
        ))}
      </div>
    );
  }

  return (
    <div
      className={cn("flex flex-wrap items-center gap-1.5", className)}
      onClick={(e) => {
        if (stopPropagation) e.stopPropagation();
      }}
    >
      {suggestions.map((s) => (
        <LegacyTagBundle key={s.id} suggestion={s} />
      ))}
    </div>
  );
}

function LegacyTagBundle({ suggestion }: { suggestion: Suggestion }) {
  const accept = useAcceptSuggestion();
  const reject = useRejectSuggestion();
  const busy = accept.isPending || reject.isPending;
  const names = tagNamesFromSuggestion(suggestion);

  return (
    <>
      {names.map((name) => (
        <div
          key={`${suggestion.id}-${name}`}
          className="rounded-md border border-dashed border-[#C9D2D8] bg-[#F1F4F6] px-1.5 py-1"
        >
          <p
            className="flex items-start gap-1 leading-snug text-xs text-[#24333D]"
            title={name}
          >
            <Sparkles
              className="mt-0.5 h-3 w-3 shrink-0 text-[#5D6B76]"
              strokeWidth={1.75}
              aria-hidden
            />
            <span>{name}</span>
          </p>
        </div>
      ))}
      <div className="flex items-center rounded-md border border-dashed border-[#C9D2D8] bg-[#F1F4F6] px-1 py-0.5">
        <SuggestionActions
          suggestionId={suggestion.id}
          field="tags"
          busy={busy}
          onAccept={(id) => accept.mutate(id)}
          onReject={(id) => reject.mutate(id)}
        />
      </div>
    </>
  );
}

interface InboxSuggestionsProps {
  documentId: string;
  /** When provided, skip the per-document fetch (table/page prefetch). */
  suggestions?: Suggestion[];
  className?: string;
  /** Show a muted empty state instead of rendering nothing. */
  showEmpty?: boolean;
  /** Section label; pass empty string to hide. */
  title?: string;
}

/** Preview sidebar list of pending AI suggestions. */
export function InboxSuggestions({
  documentId,
  suggestions: provided,
  className,
  showEmpty = false,
  title = "AI suggestions",
}: InboxSuggestionsProps) {
  const { data: fetched = [], isLoading } = useDocumentSuggestions(
    provided === undefined ? documentId : undefined,
  );
  const rows = (provided ?? fetched).filter((s) => s.document_id === documentId);

  if (provided === undefined && isLoading && rows.length === 0) {
    return (
      <p className={cn("text-xs text-text-muted", className)}>Checking AI suggestions…</p>
    );
  }

  if (rows.length === 0) {
    if (!showEmpty) return null;
    return (
      <p className={cn("text-xs text-text-muted", className)}>No pending suggestions.</p>
    );
  }

  return (
    <div className={cn("space-y-2", className)}>
      {title ? (
        <p className="text-[11px] font-medium uppercase tracking-wide text-text-muted">
          {title}
        </p>
      ) : null}
      <ul className="space-y-1.5">
        {rows.map((s) => (
          <li key={s.id}>
            <SuggestionChip suggestion={s} />
          </li>
        ))}
      </ul>
    </div>
  );
}
