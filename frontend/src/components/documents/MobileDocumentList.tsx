import { File, FileImage, FileSpreadsheet, FileText } from "lucide-react";
import type { Document, Folder, Tag as TagType } from "@/lib/api/types";
import { formatBytes, formatDate } from "@/lib/utils";
import { Checkbox } from "@/components/ui/Checkbox";
import { TagList } from "@/components/tags/TagList";
import { DocumentActionsMenu } from "@/features/documents/DocumentActionsMenu";
import { RetrievalReadinessBadge } from "@/features/documents/RetrievalReadinessBadge";

interface MobileDocumentListProps {
  documents: Document[];
  selectedIds: Set<string>;
  folders?: Folder[];
  tags?: TagType[];
  onSelect: (ids: Set<string>) => void;
  onOpen: (id: string) => void;
  onActionComplete?: () => void;
}

function FileIcon({ mimeType }: { mimeType: string }) {
  if (mimeType.startsWith("image/")) return <FileImage className="h-5 w-5 text-blue-500" />;
  if (mimeType === "application/pdf") return <FileText className="h-5 w-5 text-red-500" />;
  if (mimeType.includes("sheet") || mimeType.includes("excel")) return <FileSpreadsheet className="h-5 w-5 text-green-600" />;
  return <File className="h-5 w-5 text-text-muted" />;
}

export function MobileDocumentList({ documents, selectedIds, folders, tags, onSelect, onOpen, onActionComplete }: MobileDocumentListProps) {
  return (
    <div className="min-h-0 flex-1 divide-y divide-surface-border overflow-y-auto pb-20 md:hidden" aria-label="Documents">
      {documents.map((document) => {
        const selected = selectedIds.has(document.id);
        return (
          <article key={document.id} className={selected ? "bg-row-selected/60 px-3 py-3" : "px-3 py-3"}>
            <div className="flex min-w-0 items-start gap-2">
              <span className="pt-1" onClick={(event) => event.stopPropagation()}>
                <Checkbox checked={selected} aria-label={`Select ${document.title}`} onCheckedChange={(checked) => {
                  const next = new Set(selectedIds);
                  if (checked) next.add(document.id); else next.delete(document.id);
                  onSelect(next);
                }} />
              </span>
              <FileIcon mimeType={document.mime_type} />
              <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onOpen(document.id)}>
                <span className="block truncate text-sm font-semibold text-text-primary">{document.title || document.original_filename}</span>
                <span className="mt-1 block min-h-5"><TagList tags={document.tags} max={2} /></span>
              </button>
              <DocumentActionsMenu document={document} folders={folders} tags={tags} alwaysVisible onActionComplete={onActionComplete} triggerClassName="h-11 w-11" />
            </div>
            <div className="mt-2 flex min-w-0 items-center gap-2 pl-11 text-xs text-text-secondary">
              <RetrievalReadinessBadge document={document} />
              <span className="ml-auto shrink-0">{document.page_count ?? "—"}p · {formatBytes(document.file_size)}</span>
              <time className="shrink-0 text-text-muted" title={formatDate(document.added_date)}>{new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" }).format(new Date(document.added_date))}</time>
            </div>
          </article>
        );
      })}
    </div>
  );
}
