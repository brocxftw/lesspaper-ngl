import { type FormEvent, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { FileText, Search } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api/client";
import { useSearch } from "@/lib/api/hooks";
import type { SearchHit } from "@/lib/api/types";
import { sanitizeSearchSnippet } from "@/components/search/sanitizeSnippet";

const DEBOUNCE_MS = 300;

function documentHref(id: string, page?: number | null): string {
  const params = new URLSearchParams();
  params.set("doc", id);
  if (page && page > 1) params.set("viewerPage", String(page));
  return `/documents?${params.toString()}`;
}

export function NavbarSearch() {
  const navigate = useNavigate();
  const rootRef = useRef<HTMLFormElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const [draft, setDraft] = useState("");
  const [debounced, setDebounced] = useState("");
  const [open, setOpen] = useState(false);
  const [panelBox, setPanelBox] = useState<{ top: number; left: number; width: number } | null>(
    null,
  );

  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(draft.trim()), DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [draft]);

  const request = useMemo(
    () => ({
      query: debounced,
      mode: "keyword" as const,
      inbox: false,
      page_size: 20,
    }),
    [debounced],
  );
  const enabled = debounced.length > 0;
  const { data, isLoading, isFetching, isError } = useSearch(request, enabled);

  const showPanel = open && draft.trim().length > 0;
  const hits = data?.items ?? [];
  const searching = enabled && (isLoading || isFetching) && hits.length === 0 && !isError;

  useLayoutEffect(() => {
    if (!showPanel) {
      setPanelBox(null);
      return;
    }
    const update = () => {
      const el = inputRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      setPanelBox({
        top: rect.bottom + 8,
        left: rect.left,
        width: Math.max(rect.width, 320),
      });
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => {
      window.removeEventListener("resize", update);
      window.removeEventListener("scroll", update, true);
    };
  }, [showPanel, draft]);

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node;
      if (rootRef.current?.contains(target) || panelRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
      if (
        (event.key === "k" || event.key === "K") &&
        (event.metaKey || event.ctrlKey) &&
        !event.altKey
      ) {
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
        return;
      }
      if (
        event.key === "/" &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey
      ) {
        const target = event.target;
        if (
          target instanceof HTMLElement &&
          (target.tagName === "INPUT" ||
            target.tagName === "TEXTAREA" ||
            target.tagName === "SELECT" ||
            target.isContentEditable)
        ) {
          return;
        }
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  const openHit = (hit: SearchHit) => {
    setOpen(false);
    navigate(documentHref(hit.document.id, hit.page_number));
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (hits[0]) openHit(hits[0]);
  };

  return (
    <form
      ref={rootRef}
      role="search"
      data-tour="search"
      onSubmit={handleSubmit}
      className="relative w-[clamp(252px,25.2vw,306px)] shrink-0 lg:w-[clamp(288px,25.2vw,450px)]"
    >
      <Search
        className="pointer-events-none absolute top-1/2 left-4 h-5 w-5 -translate-y-1/2 text-[#CBD5E1]"
        aria-hidden="true"
      />
      <input
        ref={inputRef}
        type="search"
        value={draft}
        onChange={(event) => {
          setDraft(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        placeholder="Search documents, tags, folders..."
        aria-label="Search documents, tags, folders"
        aria-expanded={showPanel}
        aria-controls="navbar-search-results"
        className="h-[47px] w-full rounded-[10px] border border-[rgba(148,163,184,0.22)] bg-[rgba(30,41,59,0.72)] py-0 pr-16 pl-12 text-sm font-normal text-navbar-text shadow-[inset_0_1px_1px_rgba(255,255,255,0.025)] transition-[border-color,box-shadow] duration-150 ease-out placeholder:text-navbar-muted outline-none focus-visible:border-navbar-accent/70 focus-visible:shadow-[0_0_0_3px_var(--color-accent-ring)] focus-visible:outline-none"
      />
      {draft.trim().length === 0 ? (
        <kbd
          aria-hidden="true"
          className="pointer-events-none absolute top-1/2 right-3 -translate-y-1/2 rounded px-1.5 py-px text-[10px] font-medium leading-4 tracking-wide text-[#CBD5E1] border border-[rgba(148,163,184,0.05)] bg-[rgba(148,163,184,0.12)] shadow-[0_1px_3px_rgba(0,0,0,0.16),inset_0_1px_0_rgba(255,255,255,0.03)]"
        >
          Ctrl-K
        </kbd>
      ) : null}
      {showPanel &&
        panelBox &&
        createPortal(
          <div
            ref={panelRef}
            id="navbar-search-results"
            role="listbox"
            style={{ top: panelBox.top, left: panelBox.left, width: panelBox.width }}
            className="fixed z-[80] max-h-[min(60vh,480px)] overflow-auto rounded-[12px] border border-surface-border bg-surface text-text-primary shadow-[0_12px_32px_rgba(15,23,42,0.18)]"
          >
            {searching ? (
              <p className="px-3 py-4 text-sm text-text-muted">Searching…</p>
            ) : isError ? (
              <p className="px-3 py-4 text-sm text-text-muted">Couldn’t search the library. Try again.</p>
            ) : hits.length === 0 ? (
              <p className="px-3 py-4 text-sm text-text-muted">No matching documents</p>
            ) : (
              <ul>
                {hits.map((hit) => (
                  <li key={hit.document.id}>
                    <button
                      type="button"
                      role="option"
                      className="flex w-full items-start gap-3 px-3 py-2.5 text-left hover:bg-surface-hover"
                      onClick={() => openHit(hit)}
                    >
                      <span className="flex h-12 w-12 shrink-0 items-center justify-center overflow-hidden rounded-md bg-surface-muted">
                        {hit.document.has_thumbnail ? (
                          <img
                            src={api.thumbnailUrl(hit.document.id)}
                            alt=""
                            className="h-full w-full object-cover"
                          />
                        ) : (
                          <FileText className="h-5 w-5 text-text-muted/50" />
                        )}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">
                          {hit.document.title || hit.document.original_filename}
                        </span>
                        {hit.snippet ? (
                          <span
                            className="mt-0.5 line-clamp-2 text-xs text-text-secondary"
                            dangerouslySetInnerHTML={{
                              __html: sanitizeSearchSnippet(hit.snippet),
                            }}
                          />
                        ) : hit.document.folder_path ? (
                          <span className="mt-0.5 block truncate text-xs text-text-muted">
                            {hit.document.folder_path}
                          </span>
                        ) : null}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>,
          document.body,
        )}
    </form>
  );
}

/**
 * Mobile entry point for the same global Library search used in the desktop navbar.
 * It intentionally calls the shared /api/search retrieval endpoint with the same
 * keyword ranking semantics; it is not an Inbox filter or an Ask entry point.
 */
export function MobileNavbarSearch() {
  const navigate = useNavigate();
  const inputRef = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [debounced, setDebounced] = useState("");

  useEffect(() => {
    const handle = window.setTimeout(() => setDebounced(draft.trim()), DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [draft]);

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => inputRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  const { data, isLoading, isFetching, isError } = useSearch(
    { query: debounced, mode: "keyword", inbox: false, page_size: 20 },
    debounced.length > 0,
  );
  const hits = data?.items ?? [];
  const searching = debounced.length > 0 && (isLoading || isFetching) && hits.length === 0 && !isError;

  const openHit = (hit: SearchHit) => {
    setOpen(false);
    navigate(documentHref(hit.document.id, hit.page_number));
  };

  return (
    <div>
      <button
        type="button"
        className="flex h-11 w-11 items-center justify-center rounded-lg text-navbar-text transition-colors hover:bg-[rgba(148,163,184,0.08)]"
        aria-label="Search library"
        aria-controls="mobile-library-search"
        aria-expanded={open}
        onClick={() => setOpen((isOpen) => !isOpen)}
      >
        <Search className="h-5 w-5" aria-hidden="true" />
      </button>
      {open && (
        <section
          id="mobile-library-search"
          role="dialog"
          aria-label="Search library"
          className="fixed top-[92px] right-3 left-3 z-[80] flex max-h-[calc(100vh-108px)] flex-col overflow-hidden rounded-[14px] border border-surface-border bg-surface shadow-[0_12px_32px_rgba(15,23,42,0.22)] md:hidden"
        >
          <div className="border-b border-surface-border px-3 py-3">
            <form onSubmit={(event) => { event.preventDefault(); if (hits[0]) openHit(hits[0]); }}>
              <label className="sr-only" htmlFor="mobile-library-search-input">Search documents</label>
              <div className="relative">
                <Search className="pointer-events-none absolute top-1/2 left-3 h-5 w-5 -translate-y-1/2 text-text-muted" aria-hidden="true" />
                <input
                  id="mobile-library-search-input"
                  ref={inputRef}
                  type="search"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  placeholder="Search documents..."
                  className="h-11 w-full rounded-[10px] border border-surface-border bg-surface px-10 pr-3 text-sm text-text-primary outline-none focus-visible:ring-2 focus-visible:ring-focus"
                />
              </div>
            </form>
          </div>
          <div className="min-h-0 flex-1 overflow-auto px-4 pb-6">
            {draft.trim().length === 0 ? (
              <p className="pt-4 text-sm text-text-muted">Search your Library by document name or contents.</p>
            ) : searching ? (
              <p className="py-4 text-sm text-text-muted">Searching…</p>
            ) : isError ? (
              <p className="py-4 text-sm text-text-muted">Couldn’t search the Library. Try again.</p>
            ) : hits.length === 0 ? (
              <p className="py-4 text-sm text-text-muted">No matching documents</p>
            ) : (
              <ul className="divide-y divide-surface-border">
                {hits.map((hit) => (
                  <li key={hit.document.id}>
                    <button type="button" className="flex w-full items-start gap-3 py-3 text-left" onClick={() => openHit(hit)}>
                      <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-md bg-surface-muted">
                        {hit.document.has_thumbnail ? <img src={api.thumbnailUrl(hit.document.id)} alt="" className="h-full w-full object-cover" /> : <FileText className="h-5 w-5 text-text-muted" />}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-text-primary">{hit.document.title || hit.document.original_filename}</span>
                        <span className="mt-0.5 block truncate text-xs text-text-secondary">{hit.document.mime_type?.split("/").pop()?.toUpperCase() ?? "Document"}{hit.document.folder_path ? ` · ${hit.document.folder_path}` : ""}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      )}
    </div>
  );
}
