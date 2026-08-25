import { Download, ExternalLink, Printer, Share2 } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import { WorkerMessageHandler } from "pdfjs-dist/build/pdf.worker.min.mjs";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api/client";
import type { Document } from "@/lib/api/types";
import { shareDocument } from "@/lib/shareDocument";

// Bundle the worker into the main thread so Cursor/Electron (and other
// environments that block module Workers) can still render PDFs.
(globalThis as unknown as { pdfjsWorker?: { WorkerMessageHandler: unknown } }).pdfjsWorker = {
  WorkerMessageHandler,
};
pdfjsLib.GlobalWorkerOptions.workerSrc = `${import.meta.env.BASE_URL}pdf.worker.min.mjs`;

interface DocumentViewerProps {
  document: Document | undefined;
  page?: number;
  onPageChange?: (page: number) => void;
  /** Best-effort temporary quote highlight on the current PDF page. */
  highlightQuote?: string;
  className?: string;
}

interface HighlightRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

function normalizeQuote(value: string): string {
  return value.replace(/\s+/g, " ").trim().toLowerCase();
}

export function DocumentViewer({
  document,
  page: externalPage,
  onPageChange,
  highlightQuote,
  className,
}: DocumentViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const readerRef = useRef<HTMLDivElement>(null);
  const touchStartRef = useRef<{ x: number; y: number; distance?: number } | null>(null);
  const pdfRef = useRef<pdfjsLib.PDFDocumentProxy | null>(null);
  const renderTaskRef = useRef<pdfjsLib.RenderTask | null>(null);

  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [zoom, setZoom] = useState(100);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pdf, setPdf] = useState<pdfjsLib.PDFDocumentProxy | null>(null);
  const [fallbackUrl, setFallbackUrl] = useState<string | null>(null);
  const [highlightRects, setHighlightRects] = useState<HighlightRect[]>([]);
  const [canvasCssSize, setCanvasCssSize] = useState({ width: 0, height: 0 });
  const [readerSize, setReaderSize] = useState({ width: 0, height: 0 });

  const currentPage = externalPage ?? page;
  const docId = document?.id;
  const mime = document?.mime_type;

  useEffect(() => {
    if (externalPage !== undefined) setPage(externalPage);
  }, [externalPage]);

  useEffect(() => {
    let cancelled = false;
    let objectUrl: string | null = null;

    renderTaskRef.current?.cancel();
    renderTaskRef.current = null;
    if (pdfRef.current) {
      void pdfRef.current.destroy();
      pdfRef.current = null;
    }
    setPdf(null);
    setFallbackUrl(null);
    setError(null);
    setTotalPages(1);
    setPage(1);

    if (!docId || !mime) return;

    const isPdf = mime === "application/pdf";
    const isImage = mime.startsWith("image/");
    const isText =
      mime.startsWith("text/") || mime === "application/json" || mime === "text/markdown";

    if (!isPdf && !isImage && !isText) {
      setLoading(false);
      return;
    }

    setLoading(true);
    const url = api.downloadUrl(docId);

    void (async () => {
      try {
        const res = await fetch(url, { credentials: "include" });
        if (!res.ok) throw new Error(`Failed to download file (${res.status})`);
        const buffer = await res.arrayBuffer();
        if (cancelled) return;

        const typedBlob = new Blob([buffer], { type: mime });
        objectUrl = URL.createObjectURL(typedBlob);

        if (!isPdf) {
          setFallbackUrl(objectUrl);
          setLoading(false);
          return;
        }

        try {
          const proxy = await pdfjsLib.getDocument({ data: new Uint8Array(buffer) }).promise;
          if (cancelled) {
            void proxy.destroy();
            return;
          }
          pdfRef.current = proxy;
          setPdf(proxy);
          setTotalPages(proxy.numPages);
          setFallbackUrl(objectUrl);
          setLoading(false);
        } catch (pdfErr: unknown) {
          if (cancelled) return;
          console.warn("pdf.js failed, using native fallback", pdfErr);
          setFallbackUrl(objectUrl);
          setLoading(false);
        }
      } catch (err: unknown) {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : "Failed to load document");
        setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
      renderTaskRef.current?.cancel();
      renderTaskRef.current = null;
      if (pdfRef.current) {
        void pdfRef.current.destroy();
        pdfRef.current = null;
      }
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [docId, mime]);

  // Mobile PDFs should open fully visible, not at a fixed intrinsic scale. Keep
  // the available reader area in state so rotations and browser chrome changes
  // re-render the page at the correct fit scale.
  useLayoutEffect(() => {
    const reader = readerRef.current;
    if (!reader) return;

    const updateSize = () => {
      setReaderSize({ width: reader.clientWidth, height: reader.clientHeight });
    };
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(reader);
    return () => observer.disconnect();
  }, []);

  useLayoutEffect(() => {
    if (!pdf || mime !== "application/pdf") return;

    let cancelled = false;

    const renderPage = async () => {
      try {
        renderTaskRef.current?.cancel();
        const pdfPage = await pdf.getPage(currentPage);
        if (cancelled) return;

        const canvas = canvasRef.current;
        if (!canvas) return;

        const unscaledViewport = pdfPage.getViewport({ scale: 1 });
        const mobile = window.innerWidth < 768;
        const fitScale = Math.min(
          (readerSize.width - 8) / unscaledViewport.width,
          (readerSize.height - 8) / unscaledViewport.height,
        );
        const scale = mobile && readerSize.width && readerSize.height
          ? Math.max(0.1, fitScale) * (zoom / 100)
          : (zoom / 100) * 1.25;
        const viewport = pdfPage.getViewport({ scale });
        const outputScale = window.devicePixelRatio || 1;

        canvas.width = Math.floor(viewport.width * outputScale);
        canvas.height = Math.floor(viewport.height * outputScale);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;
        setCanvasCssSize({
          width: Math.floor(viewport.width),
          height: Math.floor(viewport.height),
        });

        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        const transform =
          outputScale !== 1 ? [outputScale, 0, 0, outputScale, 0, 0] : undefined;

        const task = pdfPage.render({
          canvasContext: ctx,
          canvas,
          viewport,
          transform,
        });
        renderTaskRef.current = task;
        await task.promise;
        if (cancelled) return;

        const quote = highlightQuote?.trim();
        if (!quote) {
          setHighlightRects([]);
          return;
        }

        try {
          const textContent = await pdfPage.getTextContent();
          const needle = normalizeQuote(quote);
          if (needle.length < 8) {
            setHighlightRects([]);
            return;
          }

          type Item = {
            str: string;
            transform: number[];
            width: number;
            height: number;
          };
          const items = (textContent.items as Item[]).filter((item) => item.str?.trim());
          const joined = items.map((item) => item.str).join(" ");
          const haystack = normalizeQuote(joined);
          const start = haystack.indexOf(needle);
          if (start < 0) {
            setHighlightRects([]);
            return;
          }

          // Map character offset in joined (with spaces) back to item indexes roughly.
          let cursor = 0;
          const matched: Item[] = [];
          const end = start + needle.length;
          for (const item of items) {
            const piece = normalizeQuote(item.str);
            if (!piece) continue;
            const next = cursor + piece.length + 1; // account for join space
            if (next > start && cursor < end) {
              matched.push(item);
            }
            cursor = next;
          }

          const rects: HighlightRect[] = matched.slice(0, 24).map((item) => {
            const tx = pdfjsLib.Util.transform(viewport.transform, item.transform);
            const x = tx[4];
            const y = tx[5];
            const fontHeight = Math.hypot(tx[2], tx[3]) || item.height || 10;
            const w =
              (item.width || 0) * (viewport.scale || scale) ||
              Math.max(8, item.str.length * 5 * (viewport.scale || scale));
            return {
              left: x,
              top: y - fontHeight,
              width: Math.max(w, 8),
              height: fontHeight * 1.15,
            };
          });
          setHighlightRects(rects);
        } catch {
          setHighlightRects([]);
        }
      } catch (err) {
        if (cancelled) return;
        if (err instanceof Error && err.name === "RenderingCancelledException") return;
        console.warn("PDF canvas render failed", err);
      }
    };

    void renderPage();
    return () => {
      cancelled = true;
      renderTaskRef.current?.cancel();
    };
  }, [pdf, mime, currentPage, zoom, highlightQuote, readerSize]);

  const goToPage = (p: number) => {
    const next = Math.max(1, Math.min(totalPages, p));
    setPage(next);
    onPageChange?.(next);
  };

  const openOriginal = () => {
    if (!document) return;
    window.open(api.downloadUrl(document.id), "_blank", "noopener,noreferrer");
  };

  const printDocument = () => {
    if (!fallbackUrl) {
      openOriginal();
      return;
    }
    const frame = window.open(fallbackUrl, "_blank", "noopener,noreferrer");
    if (!frame) return;
    const trigger = () => {
      try {
        frame.focus();
        frame.print();
      } catch {
        // Some browsers block print on blob iframes; user can print manually.
      }
    };
    frame.addEventListener("load", trigger);
    // Fallback if load already fired.
    setTimeout(trigger, 500);
  };

  const handleShare = () => {
    if (!document) return;
    void shareDocument({
      id: document.id,
      title: document.title,
      original_filename: document.original_filename,
      mime_type: document.mime_type,
    });
  };

  if (!document) {
    return (
      <div
        className={cn(
          "flex flex-1 items-center justify-center bg-white text-text-muted text-sm",
          className,
        )}
      >
        Select a document to preview
      </div>
    );
  }

  const isPdf = document.mime_type === "application/pdf";
  const isImage = document.mime_type.startsWith("image/");
  const isText =
    document.mime_type.startsWith("text/") ||
    document.mime_type === "application/json" ||
    document.mime_type === "text/markdown";
  const showCanvas = isPdf && !!pdf;

  return (
    <div className={cn("flex flex-col bg-white min-h-0", className)}>
      <div className="hidden items-center gap-1 border-b border-surface-border bg-surface px-2 py-1.5 text-text-secondary shrink-0 md:flex">
        <span className="flex-1 truncate text-xs text-text-primary">{document.title}</span>
        {isPdf && pdf && (
          <>
            <button
              type="button"
              className="h-7 w-7 rounded-md hover:bg-surface-hover disabled:opacity-40"
              onClick={() => goToPage(currentPage - 1)}
              disabled={currentPage <= 1}
              aria-label="Previous page"
            >
              ‹
            </button>
            <span className="text-xs tabular-nums">
              {currentPage} / {totalPages}
            </span>
            <button
              type="button"
              className="h-7 w-7 rounded-md hover:bg-surface-hover disabled:opacity-40"
              onClick={() => goToPage(currentPage + 1)}
              disabled={currentPage >= totalPages}
              aria-label="Next page"
            >
              ›
            </button>
            <button
              type="button"
              className="h-7 px-2 rounded-md text-xs hover:bg-surface-hover"
              onClick={() => setZoom((z) => Math.max(50, z - 10))}
            >
              −
            </button>
            <span className="text-xs w-10 text-center">{zoom}%</span>
            <button
              type="button"
              className="h-7 px-2 rounded-md text-xs hover:bg-surface-hover"
              onClick={() => setZoom((z) => Math.min(200, z + 10))}
            >
              +
            </button>
          </>
        )}
        <button
          type="button"
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-text-secondary hover:text-text-primary hover:bg-surface-hover"
          title="Open original"
          aria-label="Open original"
          onClick={openOriginal}
        >
          <ExternalLink className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-text-secondary hover:text-text-primary hover:bg-surface-hover disabled:opacity-40"
          title="Print"
          aria-label="Print"
          disabled={!fallbackUrl && !isPdf && !isImage && !isText}
          onClick={printDocument}
        >
          <Printer className="h-3.5 w-3.5" />
        </button>
        <a
          href={api.downloadUrl(document.id)}
          download={document.original_filename}
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-text-secondary hover:text-text-primary hover:bg-surface-hover"
          title="Download original"
          aria-label="Download original"
        >
          <Download className="h-3.5 w-3.5" />
        </a>
        <button
          type="button"
          className="inline-flex h-7 w-7 items-center justify-center rounded-md text-text-secondary hover:text-text-primary hover:bg-surface-hover"
          title="Share"
          aria-label="Share"
          onClick={handleShare}
        >
          <Share2 className="h-3.5 w-3.5" />
        </button>
      </div>

      <div ref={readerRef} className="relative flex-1 min-h-0 overflow-auto bg-white" onTouchStart={(event) => {
        if (window.innerWidth >= 768) return;
        const first = event.touches[0];
        const second = event.touches[1];
        touchStartRef.current = first ? { x: first.clientX, y: first.clientY, distance: second ? Math.hypot(first.clientX - second.clientX, first.clientY - second.clientY) : undefined } : null;
      }} onTouchMove={(event) => {
        if (window.innerWidth >= 768 || event.touches.length !== 2 || !touchStartRef.current?.distance) return;
        const [first, second] = [event.touches[0], event.touches[1]];
        const distance = Math.hypot(first.clientX - second.clientX, first.clientY - second.clientY);
        const factor = distance / touchStartRef.current.distance;
        setZoom((value) => Math.max(50, Math.min(200, Math.round(value * factor))));
        touchStartRef.current.distance = distance;
      }} onTouchEnd={(event) => {
        if (window.innerWidth >= 768 || !touchStartRef.current || event.changedTouches.length !== 1) return;
        const start = touchStartRef.current; const end = event.changedTouches[0]; touchStartRef.current = null;
        const dx = end.clientX - start.x; const dy = end.clientY - start.y;
        if (!start.distance && Math.abs(dx) > 80 && Math.abs(dx) > Math.abs(dy) * 1.5) goToPage(currentPage + (dx < 0 ? 1 : -1));
      }}>
        {loading && (
          <p className="absolute inset-0 z-10 flex items-center justify-center text-text-muted text-sm bg-white/80">
            Loading…
          </p>
        )}
        {error && (
          <p className="absolute inset-0 z-10 flex items-center justify-center text-danger text-sm px-4 text-center bg-white">
            {error}
          </p>
        )}

        {showCanvas && (
          <div className="flex min-h-full items-center justify-center p-1 md:items-start md:p-4">
            <div
              className="relative shadow-sm border border-surface-border bg-white"
              style={
                canvasCssSize.width
                  ? { width: canvasCssSize.width, height: canvasCssSize.height }
                  : undefined
              }
            >
              <canvas ref={canvasRef} className={cn("block", zoom > 100 ? "max-w-none" : "max-w-full")} />
              {highlightRects.map((rect, i) => (
                <div
                  key={`hl-${i}-${rect.left}-${rect.top}`}
                  aria-hidden
                  className="pointer-events-none absolute rounded-[3px] bg-amber-300/45"
                  style={{
                    left: rect.left,
                    top: rect.top,
                    width: rect.width,
                    height: rect.height,
                  }}
                />
              ))}
            </div>
          </div>
        )}

        {!showCanvas && !loading && !error && fallbackUrl && isPdf && (
          <iframe
            src={fallbackUrl}
            title={document.title}
            className="h-full w-full min-h-[480px] border-0 bg-white"
          />
        )}

        {!loading && !error && fallbackUrl && isImage && (
          <div className="flex h-full items-start justify-center overflow-auto p-4">
            <img src={fallbackUrl} alt={document.title} className="max-w-full object-contain" />
          </div>
        )}

        {!loading && !error && fallbackUrl && isText && (
          <iframe
            src={fallbackUrl}
            title={document.title}
            className="h-full w-full min-h-[480px] border-0 bg-white"
          />
        )}

        {!loading && !error && !isPdf && !isImage && !isText && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-text-muted">
            <p className="text-sm">Preview not available for this file type</p>
            <a
              href={api.downloadUrl(document.id)}
              download={document.original_filename}
              className="text-accent hover:underline text-sm"
            >
              Download {document.original_filename}
            </a>
          </div>
        )}
      </div>
      {isPdf && pdf && (
        <div className="flex h-14 shrink-0 items-center justify-between border-t border-surface-border bg-surface px-2 pb-[env(safe-area-inset-bottom)] md:hidden">
          <button type="button" className="flex h-11 min-w-11 items-center justify-center rounded-md text-text-secondary hover:bg-surface-hover disabled:opacity-40" onClick={() => goToPage(currentPage - 1)} disabled={currentPage <= 1} aria-label="Previous page">‹</button>
          <span className="text-sm tabular-nums text-text-primary">Page {currentPage} of {totalPages}</span>
          <button type="button" className="flex h-11 min-w-11 items-center justify-center rounded-md text-text-secondary hover:bg-surface-hover disabled:opacity-40" onClick={() => goToPage(currentPage + 1)} disabled={currentPage >= totalPages} aria-label="Next page">›</button>
        </div>
      )}
    </div>
  );
}
