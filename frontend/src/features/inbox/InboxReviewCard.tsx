import { useState } from "react";
import {
  CheckCheck,
  ChevronDown,
  ChevronUp,
  Eye,
  File,
  FileImage,
  FileText,
  RefreshCw,
  RotateCcw,
  Trash2,
} from "lucide-react";
import type { Document, Job, Suggestion } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { Checkbox } from "@/components/ui/Checkbox";
import { Button } from "@/components/ui/Button";
import { InboxStatusBadge } from "./InboxStatusBadge";
import { InboxProgressBar } from "./InboxProgressBar";
import { InboxAiSuggestionPanel } from "./InboxAiSuggestionPanel";
import { InboxManualFilingPanel } from "./InboxManualFilingPanel";
import { inboxRowProgress } from "./inboxPreparingPhases";
import type { SuggestionJobStatus } from "./suggestionJobStatus";
import { showSuggestionFailure } from "./suggestionJobStatus";
import { documentSecondaryMeta } from "./formatMeta";
import type { InboxAiFilingState } from "./inboxAiFiling";

function FileIcon({ doc }: { doc: Document }) {
  const mime = doc.mime_type;
  const className = "h-5 w-5 text-[#5D6B76]";
  if (mime === "application/pdf" || mime.startsWith("text/")) {
    return <FileText className={className} strokeWidth={1.75} />;
  }
  if (mime.startsWith("image/")) {
    return <FileImage className={className} strokeWidth={1.75} />;
  }
  return <File className={className} strokeWidth={1.75} />;
}

interface InboxReviewCardProps {
  document: Document;
  suggestions: Suggestion[];
  selected: boolean;
  expanded: boolean;
  /** True when this document has finished preparing and can be reviewed. */
  reviewReady?: boolean;
  /** When false, expanded review shows Manual filing instead of AI Suggestions. */
  aiSuggestionsAvailable?: boolean;
  filingUnavailableReason?: InboxAiFilingState["reason"];
  suggestionJobStatus?: SuggestionJobStatus;
  onRetrySuggestions?: () => void;
  retrySuggestionsBusy?: boolean;
  jobs?: Job[];
  acceptSuggestionsBusy?: boolean;
  onToggleExpand: () => void;
  onSelect: (selected: boolean) => void;
  onPreview: () => void;
  onRetry: () => void;
  onRemove: () => void;
  onAcceptAllSuggestions?: () => void;
}

export function InboxReviewCard({
  document: doc,
  suggestions,
  selected,
  expanded,
  reviewReady = true,
  aiSuggestionsAvailable = false,
  filingUnavailableReason,
  suggestionJobStatus = "none",
  onRetrySuggestions,
  retrySuggestionsBusy = false,
  jobs,
  acceptSuggestionsBusy = false,
  onToggleExpand,
  onSelect,
  onPreview,
  onRetry,
  onRemove,
  onAcceptAllSuggestions,
}: InboxReviewCardProps) {
  const status = doc.inbox_status;
  const [hover, setHover] = useState(false);
  const pendingCount = suggestions.length;
  const showReviewPanel = reviewReady && expanded;
  const aiSuggestionFailed =
    aiSuggestionsAvailable && showSuggestionFailure(suggestionJobStatus);
  const completed = status === "ready" || status === "needs_review";
  const rowProgress = inboxRowProgress(doc, jobs);

  return (
    <div
      className={cn(
        "mb-3.5 rounded-xl border p-5 shadow-[0_2px_6px_rgba(20,33,43,0.04)] transition-colors",
        completed
          ? "border-[var(--color-row-selected-border)] bg-[var(--color-row-selected)]"
          : hover
            ? "border-[#C7D4DA] bg-white"
            : "border-[#DCE3E8] bg-white",
      )}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div className="flex items-start gap-3.5">
        <Checkbox
          checked={selected}
          onCheckedChange={(v) => onSelect(v === true)}
          aria-label={`Select ${doc.original_filename}`}
          className="mt-3"
        />
        <div className="flex h-[46px] w-[46px] shrink-0 items-center justify-center rounded-lg bg-[#F8FAFB]">
          <FileIcon doc={doc} />
        </div>
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-[17px] font-bold leading-snug text-[#14212B]">
            {doc.original_filename}
          </h3>
          <p className="mt-1 text-xs uppercase tracking-wide text-[#74828D]">
            {documentSecondaryMeta(doc)}
          </p>
          {rowProgress && (
            <div className="mt-2.5 max-w-md">
              <p className="mb-1 text-xs text-[#5D6B76]">{rowProgress.label}</p>
              <InboxProgressBar percent={rowProgress.percent} />
            </div>
          )}
        </div>
        <InboxStatusBadge
          status={status}
          error={doc.processing_error}
          document={doc}
          jobs={jobs}
          className="shrink-0"
        />
      </div>

      {showReviewPanel &&
        (aiSuggestionFailed ? (
          <InboxManualFilingPanel
            document={doc}
            aiRetryAvailable
            onRetrySuggestions={onRetrySuggestions}
            retrySuggestionsBusy={retrySuggestionsBusy}
          />
        ) : aiSuggestionsAvailable ? (
          <InboxAiSuggestionPanel
            document={doc}
            suggestions={suggestions}
            suggestionJobStatus={suggestionJobStatus}
          />
        ) : (
          <InboxManualFilingPanel
            document={doc}
            filingUnavailableReason={filingUnavailableReason}
          />
        ))}

      <div
        className={cn(
          "mt-4 flex flex-wrap items-center justify-between gap-3",
          "md:ml-[66px]",
        )}
      >
        <button
          type="button"
          className={cn(
            "inline-flex items-center gap-1 text-xs font-medium",
            reviewReady
              ? "text-accent hover:underline"
              : "cursor-not-allowed text-[#74828D]",
          )}
          disabled={!reviewReady}
          onClick={onToggleExpand}
        >
          {!reviewReady ? (
            <>Waiting for processing…</>
          ) : expanded ? (
            <>
              <ChevronUp className="h-3.5 w-3.5" /> Collapse
            </>
          ) : (
            <>
              <ChevronDown className="h-3.5 w-3.5" /> Expand review
            </>
          )}
        </button>

        <div className="flex items-center gap-2.5">
          {reviewReady &&
            aiSuggestionsAvailable &&
            onRetrySuggestions &&
            (status === "ready" || status === "needs_review") && (
              <Button
                type="button"
                variant="outline"
                className="h-9 rounded-lg border-[#DCE3E8] px-3.5 font-semibold text-[#24333D]"
                disabled={retrySuggestionsBusy || suggestionJobStatus === "running"}
                onClick={onRetrySuggestions}
              >
                <RefreshCw
                  className={cn(
                    "h-4 w-4",
                    (retrySuggestionsBusy || suggestionJobStatus === "running") &&
                      "animate-spin",
                  )}
                  strokeWidth={1.75}
                />
                Retry Suggestions
              </Button>
            )}
          {reviewReady &&
            aiSuggestionsAvailable &&
            onAcceptAllSuggestions &&
            pendingCount > 0 && (
              <Button
                type="button"
                variant="outline"
                className="h-9 rounded-lg border-accent/40 px-3.5 font-semibold text-accent"
                disabled={acceptSuggestionsBusy}
                onClick={onAcceptAllSuggestions}
              >
                <CheckCheck className="h-4 w-4" strokeWidth={1.75} />
                Accept AI suggestions
                {pendingCount > 1 ? ` (${pendingCount})` : ""}
              </Button>
            )}
          <Button
            type="button"
            variant="outline"
            className="h-9 rounded-lg border-[#DCE3E8] px-3.5 font-semibold text-[#24333D]"
            onClick={onPreview}
          >
            <Eye className="h-4 w-4" strokeWidth={1.75} />
            Preview document
          </Button>
          {status === "failed" && (
            <Button
              type="button"
              size="icon"
              variant="outline"
              className="h-9 w-9 rounded-lg border-[#DCE3E8] text-[#5D6B76]"
              aria-label="Retry"
              onClick={onRetry}
            >
              <RotateCcw className="h-4 w-4" strokeWidth={1.75} />
            </Button>
          )}
          <Button
            type="button"
            size="icon"
            variant="outline"
            className="h-9 w-9 rounded-lg border-[#DCE3E8] text-[#C6474A] hover:bg-[#FDEBEC]"
            aria-label="Remove from queue"
            onClick={onRemove}
          >
            <Trash2 className="h-4 w-4" strokeWidth={1.75} />
          </Button>
        </div>
      </div>
    </div>
  );
}
