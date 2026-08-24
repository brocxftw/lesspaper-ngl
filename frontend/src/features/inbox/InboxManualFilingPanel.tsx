import { useEffect, useState } from "react";
import { Folder, RefreshCw } from "lucide-react";
import type { Document } from "@/lib/api/types";
import {
  useProcessInboxDocuments,
  useUpdateDocumentMetadata,
} from "@/lib/api/hooks";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { InboxFolderControl } from "./InboxFolderControl";
import { InboxTagsControl } from "./InboxTagsControl";
import { folderDisplayLabel, isSystemInboxPath } from "./formatMeta";
import type { InboxAiFilingState } from "./inboxAiFiling";

interface InboxManualFilingPanelProps {
  document: Document;
  /** When AI suggestions failed, show retry affordance above manual fields. */
  aiRetryAvailable?: boolean;
  filingUnavailableReason?: InboxAiFilingState["reason"];
  onRetrySuggestions?: () => void;
  retrySuggestionsBusy?: boolean;
}

function hasFilingDestination(doc: Document): boolean {
  if (doc.pending_folder_path) return true;
  if (doc.folder_path && !isSystemInboxPath(doc.folder_path)) return true;
  return false;
}

function formFromDoc(doc: Document) {
  return {
    title: doc.title || doc.original_filename.replace(/\.[^.]+$/, ""),
    notes: doc.notes ?? "",
    created_date: doc.created_date ?? "",
  };
}

export function InboxManualFilingPanel({
  document: doc,
  aiRetryAvailable = false,
  filingUnavailableReason,
  onRetrySuggestions,
  retrySuggestionsBusy = false,
}: InboxManualFilingPanelProps) {
  const update = useUpdateDocumentMetadata();
  const processDocs = useProcessInboxDocuments();
  const [title, setTitle] = useState(() => formFromDoc(doc).title);
  const [notes, setNotes] = useState(() => formFromDoc(doc).notes);
  const [createdDate, setCreatedDate] = useState(() => formFromDoc(doc).created_date);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const next = formFromDoc(doc);
    setTitle(next.title);
    setNotes(next.notes);
    setCreatedDate(next.created_date);
    setError(null);
  }, [doc.id, doc.title, doc.notes, doc.created_date, doc.original_filename]);

  const destinationLabel = folderDisplayLabel(doc);
  const displayPath =
    destinationLabel === "—" ? "Documents / Inbox" : destinationLabel.replace(/^\+ New:\s*/, "");
  const isNewFolder = Boolean(doc.pending_folder_path);
  const busy = update.isPending || processDocs.isPending;

  const reset = () => {
    const next = formFromDoc(doc);
    setTitle(next.title);
    setNotes(next.notes);
    setCreatedDate(next.created_date);
    setError(null);
  };

  const saveAndProcess = async () => {
    setError(null);
    const trimmedTitle = title.trim();
    if (!trimmedTitle) {
      setError("Enter a document title.");
      return;
    }

    await update.mutateAsync({
      id: doc.id,
      data: {
        title: trimmedTitle,
        notes: notes.trim() ? notes.trim() : null,
        created_date: createdDate.trim() ? createdDate.trim() : null,
        needs_review: !hasFilingDestination(doc),
      },
    });

    if (!hasFilingDestination(doc)) {
      setError("Choose a destination before processing.");
      return;
    }

    await processDocs.mutateAsync([doc.id]);
  };

  return (
    <div className="mt-5 rounded-[10px] border border-[#DCE3E8] bg-white p-[18px] shadow-[0_1px_2px_rgba(20,33,43,0.04)] md:ml-[66px]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2.5">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-muted">
            <Folder className="h-4 w-4 text-accent" strokeWidth={1.75} />
          </div>
          <div className="min-w-0">
            <h4 className="text-[15px] font-bold text-[#14212B]">Manual filing</h4>
            <p className="mt-0.5 text-xs text-[#5D6B76]">
              {filingUnavailableReason === "controls_off"
                ? "A filing model is assigned, but AI filing is turned off in AI → Controls."
                : filingUnavailableReason === "not_assigned"
                  ? "Assign a filing model in AI → Models, or file this document manually."
                  : "Review OCR output and enter document details before processing."}
            </p>
          </div>
        </div>
        <span className="shrink-0 rounded-md border border-[#B9E3CC] bg-[#E8F7EF] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#198754]">
          Manual mode
        </span>
      </div>

      {aiRetryAvailable && (
        <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5">
          <p className="text-sm text-amber-950">
            AI suggestions are unavailable. File manually below, or retry AI suggestions.
          </p>
          {onRetrySuggestions && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="mt-2 h-8 border-amber-300 bg-white text-amber-950 hover:bg-amber-100"
              disabled={retrySuggestionsBusy}
              onClick={onRetrySuggestions}
            >
              <RefreshCw
                className={`h-3.5 w-3.5 ${retrySuggestionsBusy ? "animate-spin" : ""}`}
              />
              Retry AI suggestions
            </Button>
          )}
        </div>
      )}

      <div className="mt-[18px] space-y-4">
        <div>
          <label
            htmlFor={`manual-title-${doc.id}`}
            className="text-[13px] font-bold text-[#14212B]"
          >
            Document title
          </label>
          <Input
            id={`manual-title-${doc.id}`}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="mt-2 h-10 rounded-[10px] border-[#DCE3E8] bg-white px-3.5 text-[13px]"
            disabled={busy}
          />
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div>
            <p className="text-[13px] font-bold text-[#14212B]">Destination</p>
            <div className="mt-2 rounded-[10px] border border-[#DCE3E8] bg-[#F8FAFB] px-3.5 py-2.5">
              <div className="flex items-center gap-3">
                <div className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-[9px] bg-accent-muted">
                  <Folder className="h-4 w-4 text-accent" strokeWidth={1.75} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-semibold text-[#24333D]">
                    {displayPath}
                  </p>
                  {isNewFolder && (
                    <span className="mt-1 inline-block rounded-[5px] bg-accent-muted px-[7px] py-[3px] text-[9px] font-bold uppercase tracking-wide text-accent">
                      New folder
                    </span>
                  )}
                </div>
                <InboxFolderControl
                  document={doc}
                  triggerLabel="Choose folder ›"
                  triggerClassName="shrink-0 rounded-md px-2 py-1.5 text-[11px] font-semibold text-accent hover:bg-accent-muted"
                />
              </div>
            </div>
          </div>

          <div>
            <p className="text-[13px] font-bold text-[#14212B]">Tags</p>
            <div className="mt-2 min-h-[58px] rounded-[10px] border border-[#DCE3E8] bg-white px-3 py-2.5">
              <InboxTagsControl document={doc} />
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <div>
            <label
              htmlFor={`manual-date-${doc.id}`}
              className="text-[13px] font-bold text-[#14212B]"
            >
              Document date <span className="font-normal text-[#74828D]">(optional)</span>
            </label>
            <Input
              id={`manual-date-${doc.id}`}
              type="date"
              value={createdDate}
              onChange={(e) => setCreatedDate(e.target.value)}
              className="mt-2 h-10 rounded-[10px] border-[#DCE3E8] bg-white px-3.5 text-[13px]"
              disabled={busy}
            />
          </div>

          <div>
            <label
              htmlFor={`manual-notes-${doc.id}`}
              className="text-[13px] font-bold text-[#14212B]"
            >
              Notes <span className="font-normal text-[#74828D]">(optional)</span>
            </label>
            <Textarea
              id={`manual-notes-${doc.id}`}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Add any notes about this document…"
              className="mt-2 min-h-[72px] resize-y rounded-[10px] border-[#DCE3E8] bg-white px-3.5 text-[13px]"
              disabled={busy}
            />
          </div>
        </div>
      </div>

      {error && <p className="mt-3 text-xs text-[#C6474A]">{error}</p>}

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <button
          type="button"
          className="text-xs font-medium text-[#5D6B76] hover:text-[#24333D] hover:underline disabled:opacity-50"
          disabled={busy}
          onClick={reset}
        >
          Reset
        </button>
        <Button
          type="button"
          className="h-10 rounded-lg bg-accent px-4 font-semibold text-accent-foreground hover:bg-accent-hover"
          disabled={busy}
          onClick={() => void saveAndProcess()}
        >
          {busy ? "Saving…" : "Save and process"}
        </Button>
      </div>
    </div>
  );
}
