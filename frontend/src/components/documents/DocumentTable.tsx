import { useMemo } from "react";
import { ChevronLeft, ChevronRight, FileText } from "lucide-react";
import type { Document, Folder, Tag as TagType } from "@/lib/api/types";
import { DocumentRow } from "./DocumentRow";
import { Checkbox } from "@/components/ui/Checkbox";
import { Button } from "@/components/ui/Button";
import { useDocumentSelectionModel } from "@/features/documents/useDocumentSelectionModel";
import { selectAllIds } from "@/features/documents/documentSelection";
import {
  documentListCell,
  documentListRowClass,
} from "@/features/documents/documentListColumns";
import { cn } from "@/lib/utils";
import { MobileDocumentList } from "./MobileDocumentList";

interface DocumentTableProps {
  documents: Document[];
  selectedIds: Set<string>;
  activeId?: string;
  folders?: Folder[];
  tags?: TagType[];
  onSelect: (ids: Set<string>) => void;
  onActiveChange: (id: string) => void;
  onActionComplete?: () => void;
  isLoading?: boolean;
  emptyMessage?: string;
  page?: number;
  pageSize?: number;
  total?: number;
  onPageChange?: (page: number) => void;
}

export function DocumentTable({
  documents,
  selectedIds,
  activeId,
  folders,
  tags,
  onSelect,
  onActiveChange,
  onActionComplete,
  isLoading,
  emptyMessage = "No documents in this folder",
  page = 1,
  pageSize = 50,
  total,
  onPageChange,
}: DocumentTableProps) {
  const documentIds = useMemo(() => documents.map((d) => d.id), [documents]);
  const {
    focusedIndex,
    setFocusedIndex,
    handleItemPointer,
    handleCheckbox,
    handleKeyDown,
  } = useDocumentSelectionModel({
    documentIds,
    selectedIds,
    onSelect,
    onOpen: onActiveChange,
    gridColumns: 1,
  });

  const allSelected = documents.length > 0 && documents.every((d) => selectedIds.has(d.id));
  const someSelected = documents.some((d) => selectedIds.has(d.id));
  const totalCount = total ?? documents.length;
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  const toggleAll = (checked: boolean) => {
    if (checked) onSelect(selectAllIds(documentIds));
    else onSelect(new Set());
  };

  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-text-muted">
        Loading documents…
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-2 p-8 text-center">
        <FileText className="h-10 w-10 text-text-muted/40" />
        <p className="text-sm text-text-secondary">{emptyMessage}</p>
        <p className="text-xs text-text-muted">
          Drop files or folders here — folder structure is preserved
        </p>
      </div>
    );
  }

  return (
    <>
      <MobileDocumentList
        documents={documents}
        selectedIds={selectedIds}
        folders={folders}
        tags={tags}
        onSelect={onSelect}
        onOpen={onActiveChange}
        onActionComplete={onActionComplete}
      />
    <div
      className="hidden min-h-0 flex-1 flex-col outline-none md:flex"
      tabIndex={0}
      role="grid"
      aria-multiselectable
      aria-label="Documents"
      onKeyDown={handleKeyDown}
    >
      <div className="flex-1 overflow-auto scrollbar-thin">
        <div className="min-w-[52rem] text-[13px]">
          <div
            role="row"
            className={cn(
              documentListRowClass,
              "sticky top-0 z-10 border-b border-surface-border bg-surface-muted py-2 text-left text-xs font-medium uppercase tracking-wide text-text-muted",
            )}
          >
            <div role="columnheader" className={documentListCell.checkbox}>
              <Checkbox
                checked={allSelected}
                ref={(el) => {
                  if (el) {
                    (el as unknown as HTMLInputElement).indeterminate =
                      someSelected && !allSelected;
                  }
                }}
                onCheckedChange={(c) => toggleAll(!!c)}
                aria-label="Select all on this page"
              />
            </div>
            <div role="columnheader" className={documentListCell.name}>
              Name
            </div>
            <div role="columnheader" className={documentListCell.tags}>
              Tags
            </div>
            <div role="columnheader" className={documentListCell.pages}>
              Pages / size
            </div>
            <div role="columnheader" className={documentListCell.status}>
              Status
            </div>
            <div role="columnheader" className={documentListCell.date}>
              Date
            </div>
            <div role="columnheader" className={documentListCell.actions}>
              Actions
            </div>
          </div>

          <div role="rowgroup">
            {documents.map((doc, index) => (
              <DocumentRow
                key={doc.id}
                document={doc}
                selected={selectedIds.has(doc.id)}
                active={activeId === doc.id}
                focused={focusedIndex === index}
                selectedIds={selectedIds}
                folders={folders}
                tags={tags}
                onCheckbox={(_id, checked) => handleCheckbox(index, checked)}
                onRowPointer={(_id, mods) => {
                  const action = handleItemPointer(index, mods);
                  if (action === "open") onActiveChange(doc.id);
                }}
                onOpen={onActiveChange}
                onFocusRow={() => setFocusedIndex(index)}
                onActionComplete={onActionComplete}
              />
            ))}
          </div>
        </div>
      </div>

      {onPageChange && totalPages > 1 && (
        <div className="flex items-center justify-between gap-2 border-t border-surface-border px-2 py-2">
          <span className="text-xs text-text-muted">
            Page {page} of {totalPages}
          </span>
          <div className="flex items-center gap-1">
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7"
              disabled={page <= 1}
              onClick={() => onPageChange(page - 1)}
              aria-label="Previous page"
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7"
              disabled={page >= totalPages}
              onClick={() => onPageChange(page + 1)}
              aria-label="Next page"
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
    </>
  );
}
