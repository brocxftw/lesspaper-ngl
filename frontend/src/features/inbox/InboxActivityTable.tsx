import {
  AlertCircle,
  Check,
  Clock3,
  File,
  FileImage,
  FileSpreadsheet,
  FileText,
  Loader2,
  MoreVertical,
  Eye,
  FolderInput,
  RotateCcw,
  Trash2,
  Sparkles,
} from "lucide-react";
import type { InboxActivityItem, InboxActivityStatus } from "@/lib/api/types";
import { cn, formatBytes, formatDateTime } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { TagList } from "@/components/tags/TagList";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/Tooltip";
import { fileTypeLabel, presentationLabel, processedAtValue } from "./inboxPresentation";

const BADGE_STYLES: Record<
  InboxActivityStatus,
  { className: string; icon: typeof Check }
> = {
  processed: {
    className: "bg-[#E8F7EF] text-[#198754]",
    icon: Check,
  },
  failed: {
    className: "bg-[#FDEBEC] text-[#C6474A]",
    icon: AlertCircle,
  },
  processing: {
    className: "bg-[#EAF3FE] text-[#2D6DB5]",
    icon: Loader2,
  },
  queued: {
    className: "bg-[#FFF2E3] text-[#B86B1D]",
    icon: Clock3,
  },
  needs_review: {
    className: "bg-[#FFF7DD] text-[#9D6A12]",
    icon: AlertCircle,
  },
};

function FileTypeIcon({ doc }: { doc: InboxActivityItem }) {
  const mime = doc.mime_type;
  const className = "h-4 w-4 shrink-0 text-[#5D6B76]";
  if (mime === "application/pdf" || mime.startsWith("text/")) {
    return <FileText className={className} strokeWidth={1.75} />;
  }
  if (mime.startsWith("image/")) {
    return <FileImage className={className} strokeWidth={1.75} />;
  }
  if (mime.includes("sheet") || mime === "text/csv") {
    return <FileSpreadsheet className={className} strokeWidth={1.75} />;
  }
  return <File className={className} strokeWidth={1.75} />;
}

function PresentationBadge({
  doc,
  justNow,
}: {
  doc: InboxActivityItem;
  justNow: boolean;
}) {
  if (justNow) {
    return (
      <span className="inline-flex items-center gap-1 rounded bg-[#E8F7EF] px-1.5 py-0.5 text-[11px] font-medium text-[#198754]">
        <Sparkles className="h-3 w-3" strokeWidth={1.75} />
        Just now
      </span>
    );
  }

  const status = doc.activity_status;
  const style = BADGE_STYLES[status];
  const Icon = style.icon;
  const badge = (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium",
        style.className,
      )}
    >
      <Icon
        className={cn("h-3 w-3", status === "processing" && "animate-spin")}
        strokeWidth={1.75}
      />
      {presentationLabel(status)}
    </span>
  );

  if (status === "failed" && doc.processing_error) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{badge}</TooltipTrigger>
        <TooltipContent className="max-w-[280px] text-[10px]">
          {doc.processing_error}
        </TooltipContent>
      </Tooltip>
    );
  }

  if (status === "needs_review") {
    return (
      <Tooltip>
        <TooltipTrigger asChild>{badge}</TooltipTrigger>
        <TooltipContent className="max-w-[280px] text-[10px]">
          Assign a folder or complete missing filing fields
        </TooltipContent>
      </Tooltip>
    );
  }

  return badge;
}

function compactDate(date: string | null | undefined): string {
  if (!date) return "—";
  return new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short" }).format(new Date(date));
}

interface InboxActivityTableProps {
  documents: InboxActivityItem[];
  justProcessedIds: Set<string>;
  onPreview: (id: string) => void;
  onOpenDocument: (doc: InboxActivityItem) => void;
  onRetry: (id: string) => void;
  onRemove: (id: string) => void;
  isLoading?: boolean;
  empty?: React.ReactNode;
}

export function InboxActivityTable({
  documents,
  justProcessedIds,
  onPreview,
  onOpenDocument,
  onRetry,
  onRemove,
  isLoading,
  empty,
}: InboxActivityTableProps) {
  if (isLoading) {
    return (
      <div className="flex flex-1 items-center justify-center py-16 text-sm text-text-muted">
        Loading activity…
      </div>
    );
  }

  if (documents.length === 0) {
    return <div className="flex flex-1 items-center justify-center p-8">{empty}</div>;
  }

  return (
    <>
    <div className="divide-y divide-[#EDF1F3] md:hidden">
      {documents.map((doc) => {
        const justNow = justProcessedIds.has(doc.id);
        return (
          <article key={doc.id} className={cn("px-3 py-3", justNow && "border-l-2 border-l-[#22A06B] bg-row-selected")}>
            <div className="flex min-w-0 items-start gap-2">
              <span className="mt-0.5"><FileTypeIcon doc={doc} /></span>
              <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onPreview(doc.id)}>
                <span className="block truncate text-[13px] font-medium text-[#14212B]">{doc.original_filename}</span>
                <span className="mt-0.5 block truncate text-xs text-[#74828D]">{justNow ? "Just processed" : doc.title !== doc.original_filename ? doc.title : doc.inbox ? "Added to Inbox" : "In library"}</span>
              </button>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button size="icon" variant="ghost" className="-mr-1 h-11 w-11 shrink-0 text-[#5D6B76]" aria-label="More actions">
                    <MoreVertical className="h-4 w-4" strokeWidth={1.75} />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={() => onPreview(doc.id)}>View details</DropdownMenuItem>
                  <DropdownMenuItem onClick={() => onOpenDocument(doc)}>{doc.activity_status === "processed" ? "Open in Documents" : "Open in Review & File"}</DropdownMenuItem>
                  {doc.activity_status === "failed" && <DropdownMenuItem onClick={() => onRetry(doc.id)}><RotateCcw className="h-3.5 w-3.5" />Retry</DropdownMenuItem>}
                  {doc.inbox && <DropdownMenuItem className="text-danger" onClick={() => onRemove(doc.id)}><Trash2 className="h-3.5 w-3.5" />Remove from queue</DropdownMenuItem>}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
            <div className="mt-2 flex min-w-0 items-center gap-2 pl-6 text-xs text-[#42515D]">
              <PresentationBadge doc={doc} justNow={justNow} />
              <span className="truncate">{fileTypeLabel(doc)} · {formatBytes(doc.file_size)}</span>
              <time className="ml-auto shrink-0 text-[#74828D]" title={formatDateTime(doc.added_date)}>{compactDate(doc.added_date)}</time>
            </div>
          </article>
        );
      })}
    </div>
    <div className="hidden min-h-0 flex-1 overflow-auto md:block">
      <table className="w-full min-w-[900px] border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-[#F8FAFB]">
          <tr className="h-10 border-b border-[#EDF1F3] text-left text-[11px] font-semibold text-[#5D6B76]">
            <th className="px-3 font-semibold">Document</th>
            <th className="px-3 font-semibold">Status</th>
            <th className="px-3 font-semibold">Type</th>
            <th className="px-3 font-semibold">Size</th>
            <th className="px-3 font-semibold">Uploaded</th>
            <th className="px-3 font-semibold">Processed at</th>
            <th className="px-3 font-semibold">Tags</th>
            <th className="w-[120px] px-3 text-right font-semibold">Actions</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => {
            const justNow = justProcessedIds.has(doc.id);
            const processedAt = processedAtValue(doc);
            return (
              <tr
                key={doc.id}
                className={cn(
                  "h-[58px] border-b border-[#EDF1F3] transition-colors hover:bg-[#FAFCFD]",
                  justNow && "border-l-2 border-l-[#22A06B] bg-row-selected",
                )}
              >
                <td className="px-3">
                  <button
                    type="button"
                    className="flex max-w-xs items-start gap-2 text-left"
                    onClick={() => onPreview(doc.id)}
                  >
                    <span className="mt-0.5">
                      <FileTypeIcon doc={doc} />
                    </span>
                    <span className="min-w-0">
                      <span className="block truncate text-[13px] font-medium text-[#14212B]">
                        {doc.original_filename}
                      </span>
                      <span className="block truncate text-[11px] text-[#74828D]">
                        {justNow
                          ? "Just processed"
                          : doc.title !== doc.original_filename
                            ? doc.title
                            : doc.inbox
                              ? "Added to Inbox"
                              : "In library"}
                      </span>
                    </span>
                  </button>
                </td>
                <td className="px-3">
                  <PresentationBadge doc={doc} justNow={justNow} />
                </td>
                <td className="px-3 text-xs text-[#42515D]">{fileTypeLabel(doc)}</td>
                <td className="px-3 text-xs text-[#42515D]">{formatBytes(doc.file_size)}</td>
                <td className="px-3 text-xs text-[#42515D]">{formatDateTime(doc.added_date)}</td>
                <td className="px-3 text-xs text-[#42515D]">
                  {justNow ? "Just now" : processedAt ? formatDateTime(processedAt) : "—"}
                </td>
                <td className="px-3">
                  {doc.tags.length > 0 ? (
                    <TagList tags={doc.tags} max={2} />
                  ) : (
                    <span className="text-xs text-text-muted">—</span>
                  )}
                </td>
                <td className="px-3">
                  <div className="flex items-center justify-end gap-0.5">
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-[30px] w-[30px] text-[#5D6B76]"
                      aria-label="View document"
                      onClick={() => onPreview(doc.id)}
                    >
                      <Eye className="h-4 w-4" strokeWidth={1.75} />
                    </Button>
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-[30px] w-[30px] text-[#5D6B76]"
                      aria-label={
                        doc.activity_status === "processed"
                          ? "Open in Documents"
                          : "Open in Review & File"
                      }
                      onClick={() => onOpenDocument(doc)}
                    >
                      <FolderInput className="h-4 w-4" strokeWidth={1.75} />
                    </Button>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-[30px] w-[30px] text-[#5D6B76]"
                          aria-label="More actions"
                        >
                          <MoreVertical className="h-4 w-4" strokeWidth={1.75} />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => onPreview(doc.id)}>
                          View details
                        </DropdownMenuItem>
                        <DropdownMenuItem onClick={() => onOpenDocument(doc)}>
                          {doc.activity_status === "processed"
                            ? "Open in Documents"
                            : "Open in Review & File"}
                        </DropdownMenuItem>
                        {doc.activity_status === "failed" && (
                          <DropdownMenuItem onClick={() => onRetry(doc.id)}>
                            <RotateCcw className="h-3.5 w-3.5" />
                            Retry
                          </DropdownMenuItem>
                        )}
                        {doc.inbox && (
                          <DropdownMenuItem
                            className="text-danger"
                            onClick={() => onRemove(doc.id)}
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                            Remove from queue
                          </DropdownMenuItem>
                        )}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
    </>
  );
}
