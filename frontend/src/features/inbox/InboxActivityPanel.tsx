import { useEffect, useState } from "react";
import { Filter, RefreshCw, Search } from "lucide-react";
import { useInboxActivity } from "@/lib/api/hooks";
import type { InboxActivityItem, InboxActivityStatus, InboxActivityTab } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/Popover";
import { InboxActivityTable } from "./InboxActivityTable";
import type { DateRangeDays } from "./inboxPresentation";

const TABS: { id: InboxActivityTab; label: string }[] = [
  { id: "recent", label: "Recent activity" },
  { id: "processed", label: "Processed" },
  { id: "failed", label: "Failed" },
];

const FILTER_OPTIONS: { id: InboxActivityStatus | "all"; label: string }[] = [
  { id: "all", label: "All statuses" },
  { id: "queued", label: "Queued" },
  { id: "processing", label: "Processing" },
  { id: "processed", label: "Processed" },
  { id: "needs_review", label: "Needs review" },
  { id: "failed", label: "Failed" },
];

const PAGE_SIZE = 10;

interface InboxActivityPanelProps {
  rangeDays: DateRangeDays;
  justProcessedIds: Set<string>;
  onPreview: (id: string) => void;
  onOpenDocument: (doc: InboxActivityItem) => void;
  onRetry: (id: string) => void;
  onRemove: (id: string) => void;
  onUpload: () => void;
}

export function InboxActivityPanel({
  rangeDays,
  justProcessedIds,
  onPreview,
  onOpenDocument,
  onRetry,
  onRemove,
  onUpload,
}: InboxActivityPanelProps) {
  const [tab, setTab] = useState<InboxActivityTab>("recent");
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<InboxActivityStatus | "all">("all");
  const [filterOpen, setFilterOpen] = useState(false);
  const [page, setPage] = useState(1);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedSearch(search.trim()), 250);
    return () => window.clearTimeout(t);
  }, [search]);

  const pollWhileBusy = (query: {
    state: { data?: { items?: Array<{ activity_status?: string; processing_status?: string }> } };
  }) => {
    const items = query.state.data?.items ?? [];
    const busy = items.some(
      (d) =>
        d.activity_status === "queued" ||
        d.activity_status === "processing" ||
        d.processing_status === "pending" ||
        d.processing_status === "processing",
    );
    return busy ? 3000 : false;
  };

  const { data, isLoading, isFetching, refetch } = useInboxActivity(
    {
      range_days: rangeDays,
      tab,
      q: debouncedSearch || undefined,
      page,
      page_size: PAGE_SIZE,
    },
    { refetchInterval: pollWhileBusy },
  );

  const items = (data?.items ?? []).filter((d) =>
    statusFilter === "all" ? true : d.activity_status === statusFilter,
  );
  const total = data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);

  useEffect(() => {
    if (page > totalPages) setPage(totalPages);
  }, [page, totalPages]);

  const emptyCopy = (() => {
    if (tab === "failed") {
      return {
        title: "No failed documents",
        body: "Everything in this range was processed successfully.",
      };
    }
    if (tab === "processed") {
      return {
        title: "No processed documents",
        body: "Processed documents will appear here once ingestion completes.",
      };
    }
    return {
      title: "No ingestion activity yet",
      body: "Upload documents to start building your ingestion history.",
    };
  })();

  return (
    <section className="mt-6 overflow-hidden rounded-[10px] border border-[#DCE3E8] bg-white md:mt-4">
      <div className="flex items-center justify-between px-3 pt-3 md:hidden">
        <h2 className="text-base font-bold text-[#14212B]">Recent activity</h2>
        <Button size="icon" variant="ghost" className="h-11 w-11" aria-label="Refresh activity" disabled={isFetching} onClick={() => void refetch()}>
          <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} strokeWidth={1.75} />
        </Button>
      </div>
      <div className="flex flex-wrap items-center gap-3 border-b border-[#E7ECEF] px-3 pb-3 pt-2 md:px-4 md:py-3">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => {
                setTab(t.id);
                setPage(1);
              }}
              className={cn(
                "border-b-2 px-2.5 py-2 text-xs font-medium transition-colors md:py-1.5",
                tab === t.id
                  ? "border-accent text-accent"
                  : "border-transparent text-[#5D6B76] hover:text-[#14212B]",
              )}
            >
              {t.id === "recent" ? <><span className="md:hidden">All</span><span className="hidden md:inline">{t.label}</span></> : t.label}
            </button>
          ))}
        </div>

        <div className="flex w-full items-center gap-2 md:w-auto md:flex-wrap">
          <div className="relative min-w-0 flex-1 md:w-[280px] md:flex-none">
            <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#74828D]" />
            <Input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Filter activity..."
              className="h-11 pl-8 text-sm md:h-[30px] md:text-xs"
            />
          </div>

          <Popover open={filterOpen} onOpenChange={setFilterOpen}>
            <PopoverTrigger asChild>
              <Button
                size="sm"
                variant="outline"
                className={cn(
                  "h-11 shrink-0 px-3 md:h-[30px] md:px-2",
                  statusFilter !== "all" && "border-accent text-accent",
                )}
              >
                <Filter className="h-3.5 w-3.5" strokeWidth={1.75} />
                <span className="md:hidden">Filter</span><span className="hidden md:inline">Filter</span>
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-48 p-1">
              {FILTER_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  type="button"
                  className={cn(
                    "block w-full rounded px-2 py-1.5 text-left text-xs hover:bg-surface-hover",
                    statusFilter === opt.id && "bg-surface-muted font-medium",
                  )}
                  onClick={() => {
                    setStatusFilter(opt.id);
                    setPage(1);
                    setFilterOpen(false);
                  }}
                >
                  {opt.label}
                </button>
              ))}
            </PopoverContent>
          </Popover>

          <Button
            size="icon"
            variant="outline"
            className="hidden h-[30px] w-[30px] md:inline-flex"
            aria-label="Refresh"
            title="Refresh"
            disabled={isFetching}
            onClick={() => void refetch()}
          >
            <RefreshCw
              className={cn("h-3.5 w-3.5", isFetching && "animate-spin")}
              strokeWidth={1.75}
            />
          </Button>
        </div>
      </div>

      <InboxActivityTable
        documents={items}
        justProcessedIds={justProcessedIds}
        onPreview={onPreview}
        onOpenDocument={onOpenDocument}
        onRetry={onRetry}
        onRemove={onRemove}
        isLoading={isLoading}
        empty={
          <div className="max-w-sm py-6 text-center">
            <p className="text-sm font-medium text-[#14212B]">{emptyCopy.title}</p>
            <p className="mt-1 text-xs text-[#42515D]">{emptyCopy.body}</p>
            {tab === "recent" && (
              <Button size="sm" className="mt-4" onClick={onUpload}>
                Upload documents
              </Button>
            )}
          </div>
        }
      />

      <div className="flex items-center justify-between border-t border-[#E7ECEF] px-3 py-2.5 text-xs text-[#74828D] md:px-4">
        <span className="min-w-0 truncate">
          {total === 0
            ? "Showing 0 documents"
            : `Showing ${(safePage - 1) * PAGE_SIZE + 1} to ${Math.min(safePage * PAGE_SIZE, total)} of ${total} documents`}
        </span>
        {total > PAGE_SIZE && (
          <div className="flex items-center gap-1">
            {Array.from({ length: totalPages }, (_, i) => i + 1)
              .slice(Math.max(0, safePage - 3), Math.max(0, safePage - 3) + 5)
              .map((p) => (
                <button
                  key={p}
                  type="button"
                  onClick={() => setPage(p)}
                  className={cn(
                    "flex h-11 min-w-11 items-center justify-center rounded px-2 text-xs font-medium md:h-[30px] md:min-w-[30px]",
                    p === safePage
                      ? "bg-accent text-accent-foreground"
                      : "text-[#5D6B76] hover:bg-surface-hover",
                  )}
                >
                  {p}
                </button>
              ))}
          </div>
        )}
      </div>
    </section>
  );
}
