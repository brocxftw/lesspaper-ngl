import { Folder, Loader2, Sparkles } from "lucide-react";
import type { Document, Suggestion } from "@/lib/api/types";
import { InboxFolderControl } from "./InboxFolderControl";
import { InboxTagsControl } from "./InboxTagsControl";
import { folderDisplayLabel } from "./formatMeta";
import { SuggestionChip, TagSuggestionTiles } from "./InboxSuggestions";
import type { SuggestionJobStatus } from "./suggestionJobStatus";

interface InboxAiSuggestionPanelProps {
  document: Document;
  suggestions: Suggestion[];
  suggestionJobStatus?: SuggestionJobStatus;
}

function confidencePercent(suggestions: Suggestion[]): string | null {
  const values = suggestions
    .map((s) => s.confidence)
    .filter((c): c is number => typeof c === "number" && Number.isFinite(c));
  if (values.length === 0) return null;
  const avg = values.reduce((a, b) => a + b, 0) / values.length;
  const pct = avg <= 1 ? avg * 100 : avg;
  return `${Math.round(pct)}%`;
}

export function InboxAiSuggestionPanel({
  document: doc,
  suggestions,
  suggestionJobStatus = "none",
}: InboxAiSuggestionPanelProps) {
  const folderSuggestion = suggestions.find((s) => s.field === "folder");
  const tagSuggestions = suggestions.filter((s) => s.field === "tags");
  const titleSuggestion = suggestions.find((s) => s.field === "title");
  const otherSuggestions = suggestions.filter(
    (s) => s.field !== "folder" && s.field !== "tags" && s.field !== "title",
  );

  const destination = folderDisplayLabel(doc);
  const isNewFolder = Boolean(doc.pending_folder_path);
  const hasDestination = destination !== "—";
  const suggestedPath =
    folderSuggestion && typeof folderSuggestion.value.path === "string"
      ? folderSuggestion.value.path
      : null;
  const suggestedCreate = folderSuggestion?.value.create === true;
  const displayPath = hasDestination
    ? destination.replace(/^\+ New:\s*/, "")
    : suggestedPath || "No destination set";

  const confidence = confidencePercent(suggestions);
  const isGenerating = suggestionJobStatus === "running";
  const noSuggestions =
    !isGenerating &&
    suggestions.length === 0 &&
    suggestionJobStatus === "empty" &&
    !hasDestination &&
    (doc.tags?.length ?? 0) === 0;

  return (
    <div className="mt-5 rounded-[10px] border border-accent/30 bg-gradient-to-br from-accent-muted/40 to-accent-muted p-[18px] md:ml-[66px]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-wrap items-start gap-2">
          <Sparkles className="mt-0.5 h-4 w-4 shrink-0 text-accent" strokeWidth={1.75} />
          <div className="min-w-0">
            <h4 className="text-[15px] font-bold text-[#14212B]">AI Suggestions</h4>
            <p className="mt-0.5 text-xs text-[#5D6B76]">
              Review the AI suggested destination and tags before processing.
            </p>
          </div>
        </div>
        <div className="ml-auto shrink-0 text-right">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-[#74828D]">
            Confidence
          </p>
          <p
            className="mt-0.5 text-[15px] font-bold tabular-nums text-accent"
            title={
              confidence === null && suggestions.length > 0
                ? "The model did not return confidence scores for these suggestions"
                : undefined
            }
          >
            {confidence ?? (suggestions.length > 0 ? "Unavailable" : "—")}
          </p>
        </div>
      </div>

      {isGenerating ? (
        <div className="mt-4 flex items-center gap-2 rounded-lg border border-accent/30 bg-white/80 px-3 py-2.5 text-sm text-[#24333D]">
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-accent" />
          Generating AI suggestions…
        </div>
      ) : noSuggestions ? (
        <p className="mt-4 text-sm text-[#5D6B76]">
          No AI suggestions were generated. Use Retry Suggestions or file manually.
        </p>
      ) : (
        <>
          {titleSuggestion && (
            <div className="mt-[18px]">
              <p className="text-[13px] font-bold text-[#14212B]">Filename</p>
              <div className="mt-3">
                <SuggestionChip suggestion={titleSuggestion} />
              </div>
            </div>
          )}

          <div className="mt-[18px] grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_1px_minmax(0,1.1fr)]">
            <div>
              <p className="text-[13px] font-bold text-[#14212B]">Destination</p>
              <div className="mt-3.5 rounded-[10px] border border-[#DCE3E8] bg-white px-3.5 py-2.5">
                <div className="flex items-center gap-3">
                  <div className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-[9px] bg-accent-muted">
                    <Folder className="h-4 w-4 text-accent" strokeWidth={1.75} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-semibold text-[#24333D]">{displayPath}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2">
                      {(isNewFolder || suggestedCreate) && (
                        <span className="rounded-[5px] bg-accent-muted px-[7px] py-[3px] text-[9px] font-bold uppercase tracking-wide text-accent">
                          New folder
                        </span>
                      )}
                    </div>
                  </div>
                  <InboxFolderControl document={doc} triggerLabel="Change destination" />
                </div>

                {folderSuggestion && !hasDestination && (
                  <div className="mt-3">
                    <SuggestionChip suggestion={folderSuggestion} />
                  </div>
                )}
              </div>
            </div>

            <div className="hidden bg-[#DCE3E8] lg:block" aria-hidden />

            <div>
              <p className="text-[13px] font-bold text-[#14212B]">Tags</p>
              <div className="mt-3.5">
                <InboxTagsControl document={doc} />
              </div>
              {tagSuggestions.length > 0 && (
                <div className="mt-3">
                  <TagSuggestionTiles suggestions={tagSuggestions} />
                </div>
              )}
            </div>
          </div>

          {otherSuggestions.length > 0 && (
            <div className="mt-4 flex flex-wrap gap-2 border-t border-accent/30 pt-4">
              {otherSuggestions.map((s) => (
                <SuggestionChip key={s.id} suggestion={s} compact />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
