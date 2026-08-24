import { useCallback, useRef, useState, type DragEvent, type ReactNode } from "react";
import { FolderUp, Upload } from "lucide-react";
import { cn } from "@/lib/utils";
import {
  captureDataTransferItems,
  dataTransferHasFiles,
  resolvePendingItems,
  type UploadEntry,
} from "@/lib/uploadTree";

interface UploadDropzoneProps {
  /** Called with collected files/folders after a successful drop. */
  onEntries: (entries: UploadEntry[]) => void | Promise<void>;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
}

/**
 * Full-area drop target that accepts individual files and folders.
 * Captures FileSystem entries synchronously on drop (required by browsers),
 * then expands folders asynchronously before invoking ``onEntries``.
 */
export function UploadDropzone({
  onEntries,
  children,
  className,
  disabled,
}: UploadDropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const depthRef = useRef(0);

  const resetDrag = useCallback(() => {
    depthRef.current = 0;
    setDragging(false);
  }, []);

  const handleDragEnter = (e: DragEvent) => {
    if (disabled || !dataTransferHasFiles(e.dataTransfer)) return;
    e.preventDefault();
    e.stopPropagation();
    depthRef.current += 1;
    setDragging(true);
  };

  const handleDragLeave = (e: DragEvent) => {
    if (disabled) return;
    e.preventDefault();
    e.stopPropagation();
    depthRef.current = Math.max(0, depthRef.current - 1);
    if (depthRef.current === 0) setDragging(false);
  };

  const handleDragOver = (e: DragEvent) => {
    if (disabled || !dataTransferHasFiles(e.dataTransfer)) return;
    e.preventDefault();
    e.stopPropagation();
    e.dataTransfer.dropEffect = "copy";
  };

  const handleDrop = (e: DragEvent) => {
    if (disabled) return;
    e.preventDefault();
    e.stopPropagation();
    resetDrag();

    // Capture entries before the event ends — DataTransfer is cleared afterward.
    const pending = captureDataTransferItems(e.dataTransfer);
    if (pending.length === 0) return;

    void (async () => {
      const entries = await resolvePendingItems(pending);
      if (entries.length === 0) return;
      await onEntries(entries);
    })();
  };

  return (
    <div
      className={cn("relative flex flex-col", className)}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {children}
      {dragging && !disabled && (
        <div className="pointer-events-none absolute inset-0 z-40 flex items-center justify-center bg-accent/10 backdrop-blur-[1px]">
          <div className="flex flex-col items-center gap-2 rounded-lg border-2 border-dashed border-accent bg-surface px-8 py-6 shadow-sm">
            <div className="flex items-center gap-3 text-accent">
              <Upload className="h-6 w-6" />
              <FolderUp className="h-6 w-6" />
            </div>
            <p className="text-sm font-medium text-text-primary">Drop files or folders</p>
            <p className="text-xs text-text-muted">
              Folder structure will be recreated in lesspaper-ngl
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
