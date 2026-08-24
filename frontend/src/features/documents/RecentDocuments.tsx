import { useState } from "react";
import { ChevronDown, ChevronRight, FileText } from "lucide-react";
import { api } from "@/lib/api/client";
import { cn, formatDate } from "@/lib/utils";
import type { Document } from "@/lib/api/types";
import { RetrievalReadinessBadge } from "./RetrievalReadinessBadge";

const RECENTS_COLLAPSED_KEY = "lesspaper-ngl.documents.recentsCollapsed";
const RECENTS_COLLAPSED_KEY_LEGACY = "folium.documents.recentsCollapsed";

function readCollapsed(): boolean {
  try {
    let raw = localStorage.getItem(RECENTS_COLLAPSED_KEY);
    if (raw == null) {
      raw = localStorage.getItem(RECENTS_COLLAPSED_KEY_LEGACY);
      if (raw != null) {
        localStorage.setItem(RECENTS_COLLAPSED_KEY, raw);
      }
    }
    return raw === "1";
  } catch {
    return false;
  }
}

interface RecentDocumentsProps {
  documents: Document[];
  onOpen: (id: string) => void;
  className?: string;
}

export function RecentDocuments({ documents, onOpen, className }: RecentDocumentsProps) {
  const [collapsed, setCollapsed] = useState(readCollapsed);

  if (documents.length === 0) return null;

  const toggle = () => {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem(RECENTS_COLLAPSED_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });
  };

  return (
    <section className={cn("space-y-2", className)}>
      <button
        type="button"
        onClick={toggle}
        className="flex w-full items-center gap-1 text-left text-xs font-medium uppercase tracking-wide text-text-muted hover:text-text-secondary"
        aria-expanded={!collapsed}
      >
        {collapsed ? (
          <ChevronRight className="h-3.5 w-3.5 shrink-0" />
        ) : (
          <ChevronDown className="h-3.5 w-3.5 shrink-0" />
        )}
        Recently added
      </button>
      {!collapsed && (
        <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
          {documents.map((doc) => (
            <button
              key={doc.id}
              type="button"
              onClick={() => onOpen(doc.id)}
              className="group flex flex-col overflow-hidden rounded-md border border-surface-border bg-surface text-left transition-colors hover:border-accent/40 hover:bg-surface-hover"
            >
              <div className="flex aspect-[5/3] items-center justify-center bg-surface-muted">
                {doc.has_thumbnail ? (
                  <img
                    src={api.thumbnailUrl(doc.id)}
                    alt=""
                    className="h-full w-full object-cover"
                    loading="lazy"
                  />
                ) : (
                  <FileText className="h-5 w-5 text-text-muted/50" />
                )}
              </div>
              <div className="space-y-0.5 px-1.5 py-1">
                <p className="truncate text-[12px] font-medium text-text-primary group-hover:text-accent">
                  {doc.title}
                </p>
                <div className="flex items-center justify-between gap-1">
                  <span className="truncate text-[10px] text-text-muted">
                    {formatDate(doc.added_date)}
                  </span>
                  <RetrievalReadinessBadge document={doc} className="shrink-0 scale-90 origin-right" />
                </div>
              </div>
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
