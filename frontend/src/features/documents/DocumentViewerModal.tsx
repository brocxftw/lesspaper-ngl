import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, MoreHorizontal, Trash2 } from "lucide-react";
import { useDocument, useTrashDocument } from "@/lib/api/hooks";
import type { Citation, Folder } from "@/lib/api/types";
import { DocumentViewer } from "@/components/viewer/DocumentViewer";
import { DocumentInspector } from "@/components/inspector/DocumentInspector";
import { Breadcrumbs } from "@/components/documents/Breadcrumbs";
import { DocumentAskPanel } from "@/components/ask/DocumentAskPanel";
import { AskFab } from "@/components/ask/AskFab";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogClose,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/Sheet";
import { RetrievalReadinessBadge } from "./RetrievalReadinessBadge";
import { canAskDocument } from "./retrievalReadiness";

interface DocumentViewerModalProps {
  activeId: string | null;
  page?: number;
  folders: Folder[];
  onActiveIdChange: (id: string | null) => void;
  onPageChange?: (page: number) => void;
  onNavigateToFolder?: (folderId: string | undefined) => void;
  onTrashed?: (documentId: string) => void;
}

interface ActiveHighlight {
  page: number;
  quote: string;
}

export function DocumentViewerModal({
  activeId,
  page,
  folders,
  onActiveIdChange,
  onPageChange,
  onNavigateToFolder,
  onTrashed,
}: DocumentViewerModalProps) {
  const open = Boolean(activeId);
  const { data: doc } = useDocument(activeId ?? undefined);
  const trashDocument = useTrashDocument();
  const [confirmTrash, setConfirmTrash] = useState(false);
  const [askOpen, setAskOpen] = useState(false);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const [highlight, setHighlight] = useState<ActiveHighlight | null>(null);

  useEffect(() => {
    if (!open) {
      setAskOpen(false);
      setDetailsOpen(false);
      setHighlight(null);
    }
  }, [open]);

  useEffect(() => {
    setAskOpen(false);
    setDetailsOpen(false);
    setHighlight(null);
  }, [activeId]);

  const handleTrash = async () => {
    if (!doc) return;
    await trashDocument.mutateAsync(doc.id);
    setConfirmTrash(false);
    onTrashed?.(doc.id);
    onActiveIdChange(null);
  };

  const handleCitation = (citation: Citation) => {
    if (citation.document_id === activeId && citation.page_number != null) {
      onPageChange?.(citation.page_number);
      if (citation.quote) {
        setHighlight({ page: citation.page_number, quote: citation.quote });
      } else {
        setHighlight(null);
      }
      return;
    }
    if (citation.document_id !== activeId) {
      onActiveIdChange(citation.document_id);
      if (citation.page_number != null) onPageChange?.(citation.page_number);
      setHighlight(null);
    }
  };

  const viewerHighlightQuote = useMemo(() => {
    if (!highlight || page == null) return undefined;
    if (highlight.page !== page) return undefined;
    return highlight.quote;
  }, [highlight, page]);

  return (
    <>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!next) onActiveIdChange(null);
        }}
      >
        <DialogContent className="flex h-dvh w-screen max-w-none flex-col gap-0 overflow-hidden rounded-none border-0 p-0 [&>button:last-child]:hidden md:h-[95vh] md:w-[95vw] md:rounded-lg md:border md:[&>button:last-child]:block">
          <DialogHeader className="mb-0 flex flex-row items-center justify-between gap-3 space-y-0 border-b border-surface-border px-3 py-2 pr-3 pt-[max(0.5rem,env(safe-area-inset-top))] md:items-start md:px-4 md:py-3 md:pr-12">
            <DialogClose className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md text-text-secondary hover:bg-surface-hover md:hidden" aria-label="Close document"><ChevronLeft className="h-5 w-5" /></DialogClose>
            <div className="flex min-w-0 flex-1 items-center justify-center md:block">
              <DialogTitle className="truncate text-center text-base md:text-left">
                {doc?.title || doc?.original_filename || "Document"}
              </DialogTitle>
              {doc && (
                <Breadcrumbs
                  className="mt-1 hidden md:flex"
                  folderId={doc.folder_id ?? undefined}
                  folders={folders}
                  onNavigate={
                    onNavigateToFolder
                      ? (folderId) => onNavigateToFolder(folderId)
                      : undefined
                  }
                />
              )}
              {doc && (
                <div className="mt-1 hidden flex-wrap items-center gap-2 md:flex">
                  <RetrievalReadinessBadge document={doc} />
                  {!canAskDocument(doc) && (
                    <span className="text-[11px] text-text-muted">
                      Not ready for Ask yet — indexing still needed
                    </span>
                  )}
                </div>
              )}
            </div>
            <div className="flex shrink-0 items-center gap-1">
              <Button size="icon" variant="ghost" className="h-11 w-11 md:hidden" aria-label="Document details" onClick={() => setDetailsOpen(true)}><MoreHorizontal className="h-5 w-5" /></Button>
              {doc && (
                <Button
                  size="sm"
                  variant="ghost"
                  className="mr-1 hidden text-danger hover:text-danger md:inline-flex"
                  disabled={trashDocument.isPending}
                  onClick={() => setConfirmTrash(true)}
                  aria-label="Move to trash"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Trash
                </Button>
              )}
            </div>
          </DialogHeader>

          <div className="flex min-h-0 flex-1">
            <div className="relative min-w-0 flex-1 bg-surface-muted">
              <DocumentViewer
                document={doc}
                page={page}
                onPageChange={onPageChange}
                highlightQuote={viewerHighlightQuote}
                className="h-full"
              />
              {!askOpen && doc && canAskDocument(doc) && (
                <AskFab
                  onClick={() => setAskOpen(true)}
                  className="absolute right-4 bottom-4 z-10 hidden md:flex"
                />
              )}
              {!askOpen && doc && canAskDocument(doc) && (
                <Button size="sm" className="absolute right-3 bottom-16 z-10 h-10 rounded-full px-4 md:hidden" onClick={() => setAskOpen(true)}>Ask AI</Button>
              )}
            </div>
            {/* Inspector when Ask closed; Ask replaces this rail when open (same width). */}
            <aside className={askOpen ? "fixed inset-0 z-20 flex w-full flex-col overflow-hidden bg-surface md:relative md:z-auto md:w-[440px] md:shrink-0 md:border-l" : "relative hidden w-[440px] shrink-0 flex-col overflow-hidden border-l border-surface-border bg-surface md:flex"}>
              {askOpen && doc ? (
                <DocumentAskPanel
                  documentId={doc.id}
                  documentTitle={doc.title || doc.original_filename}
                  active={askOpen}
                  onClose={() => setAskOpen(false)}
                  onCitationActivate={handleCitation}
                  className="h-full"
                />
              ) : (
                <DocumentInspector document={doc} />
              )}
            </aside>
          </div>
        </DialogContent>
      </Dialog>

      <Sheet open={detailsOpen} onOpenChange={setDetailsOpen}>
        <SheetContent side="right" className="!w-[min(88vw,380px)] !max-w-none p-0 md:hidden">
          <SheetHeader><SheetTitle>Document details</SheetTitle></SheetHeader>
          <div className="min-h-0 flex-1 overflow-y-auto"><DocumentInspector document={doc} /></div>
        </SheetContent>
      </Sheet>

      <Dialog open={confirmTrash} onOpenChange={setConfirmTrash}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Move to Trash</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-text-secondary">
            Move &ldquo;{doc?.title || doc?.original_filename || "this document"}&rdquo; to Trash?
            You can restore it later from Trash.
          </p>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setConfirmTrash(false)}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={trashDocument.isPending}
              onClick={() => void handleTrash()}
            >
              Move to Trash
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
