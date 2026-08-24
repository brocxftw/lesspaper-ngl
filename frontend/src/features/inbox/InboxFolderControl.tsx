import { useMemo, useState } from "react";
import type { Document, Folder } from "@/lib/api/types";
import { useFolders, useUpdateDocumentMetadata } from "@/lib/api/hooks";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/Popover";
import { cn } from "@/lib/utils";
import { folderDisplayLabel } from "./formatMeta";

interface InboxFolderControlProps {
  document: Document;
  stopPropagation?: boolean;
  /** Override the trigger label (defaults to the current folder path). */
  triggerLabel?: string;
  triggerClassName?: string;
}

function isAssignable(f: Folder): boolean {
  return f.kind === "normal";
}

export function InboxFolderControl({
  document: doc,
  stopPropagation,
  triggerLabel,
  triggerClassName,
}: InboxFolderControlProps) {
  const { data: folders = [] } = useFolders();
  const update = useUpdateDocumentMetadata();
  const [open, setOpen] = useState(false);
  const [newPath, setNewPath] = useState("");

  const destinations = useMemo(
    () =>
      folders
        .filter(isAssignable)
        .sort((a, b) => a.path_cache.localeCompare(b.path_cache)),
    [folders],
  );

  const label = folderDisplayLabel(doc);
  const isNew = Boolean(doc.pending_folder_path);
  const buttonLabel = triggerLabel ?? label;

  const assignFolder = async (folderId: string) => {
    await update.mutateAsync({
      id: doc.id,
      data: { folder_id: folderId, pending_folder_path: null, needs_review: false },
    });
    setOpen(false);
  };

  const assignNewPath = async () => {
    const path = newPath.trim();
    if (!path) return;
    await update.mutateAsync({
      id: doc.id,
      data: { pending_folder_path: path, needs_review: false },
    });
    setNewPath("");
    setOpen(false);
  };

  const clear = async () => {
    await update.mutateAsync({
      id: doc.id,
      data: { pending_folder_path: null, needs_review: true },
    });
    setOpen(false);
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cn(
            triggerLabel
              ? "shrink-0 rounded-md px-2.5 py-1.5 text-[11px] font-semibold text-accent hover:bg-accent-muted"
              : cn(
                  "max-w-[180px] truncate rounded px-1.5 py-0.5 text-left text-xs hover:bg-surface-hover",
                  isNew ? "text-emerald-800 font-medium" : "text-text-primary",
                  label === "—" && "text-text-muted",
                ),
            triggerClassName,
          )}
          onClick={(e) => {
            if (stopPropagation) e.stopPropagation();
          }}
        >
          {buttonLabel}
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="w-72 p-2"
        onClick={(e) => stopPropagation && e.stopPropagation()}
      >
        <p className="px-1 pb-1 text-[11px] font-medium text-text-secondary">Assign folder</p>
        <div className="max-h-40 overflow-y-auto">
          {destinations.map((f) => (
            <button
              key={f.id}
              type="button"
              className="block w-full truncate rounded px-2 py-1.5 text-left text-xs hover:bg-surface-hover"
              onClick={() => void assignFolder(f.id)}
            >
              {f.path_cache}
            </button>
          ))}
          {destinations.length === 0 && (
            <p className="px-2 py-2 text-xs text-text-muted">No folders yet</p>
          )}
        </div>
        <div className="mt-2 border-t border-surface-border pt-2 space-y-1.5">
          <p className="px-1 text-[11px] font-medium text-text-secondary">New folder path</p>
          <Input
            value={newPath}
            onChange={(e) => setNewPath(e.target.value)}
            placeholder="Finance / Insurance / Vehicle"
            className="h-7 text-xs"
            onKeyDown={(e) => {
              if (e.key === "Enter") void assignNewPath();
            }}
          />
          <div className="flex gap-1">
            <Button
              size="sm"
              className="h-7 text-xs"
              disabled={!newPath.trim() || update.isPending}
              onClick={() => void assignNewPath()}
            >
              Use new path
            </Button>
            {(doc.pending_folder_path || (doc.folder_path && label !== "—")) && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={() => void clear()}
              >
                Clear
              </Button>
            )}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
