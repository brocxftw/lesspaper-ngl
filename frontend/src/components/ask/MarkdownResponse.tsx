import {
  Children,
  cloneElement,
  isValidElement,
  useState,
  type ReactNode,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ExternalLink } from "lucide-react";
import { cn } from "@/lib/utils";
import type { AskCitationSnapshot, Citation } from "@/lib/api/types";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/Popover";
import { rewriteChunkMarkersForDisplay } from "./citationNormalize";

export function toCitation(c: AskCitationSnapshot | Citation): Citation {
  const anyC = c as AskCitationSnapshot & Partial<Citation>;
  return {
    document_id: anyC.document_id,
    page_number: anyC.page_number,
    chunk_id: anyC.chunk_id,
    title: (anyC.title as string | null | undefined) ?? "Source",
    quote: anyC.quote ?? null,
    display_number: anyC.display_number,
  };
}

const CITATION_TOKEN = /\[(\d+)\]/g;

function injectCitations(
  node: ReactNode,
  byNumber: Map<number, Citation>,
  activeNumber: number | null | undefined,
  onActivate: (citation: Citation) => void,
): ReactNode {
  return Children.map(node, (child, index) => {
    if (typeof child === "string") {
      return renderTextWithCitations(child, byNumber, activeNumber, onActivate, index);
    }
    if (!isValidElement<{ children?: ReactNode }>(child)) {
      return child;
    }
    if (child.props.children == null) {
      return child;
    }
    return cloneElement(child, {
      ...child.props,
      children: injectCitations(
        child.props.children,
        byNumber,
        activeNumber,
        onActivate,
      ),
    });
  });
}

function renderTextWithCitations(
  text: string,
  byNumber: Map<number, Citation>,
  activeNumber: number | null | undefined,
  onActivate: (citation: Citation) => void,
  keyPrefix: number | string,
): ReactNode {
  const parts: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  const re = new RegExp(CITATION_TOKEN.source, "g");
  while ((match = re.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    const n = Number(match[1]);
    const citation = byNumber.get(n);
    if (citation) {
      parts.push(
        <InlineCitation
          key={`${keyPrefix}-${match.index}-${n}`}
          citation={{ ...citation, display_number: n }}
          active={activeNumber === n}
          onActivate={onActivate}
        />,
      );
    } else {
      // Unvalidated marker — never promote to a citation control.
      parts.push(match[0]);
    }
    last = match.index + match[0].length;
  }
  if (last < text.length) {
    parts.push(text.slice(last));
  }
  return parts;
}

interface InlineCitationProps {
  citation: Citation;
  active?: boolean;
  onActivate: (citation: Citation) => void;
}

export function InlineCitation({ citation, active, onActivate }: InlineCitationProps) {
  const [open, setOpen] = useState(false);
  const n = citation.display_number ?? 0;
  const label = `Source ${n}${citation.title ? `, ${citation.title}` : ""}${
    citation.page_number != null ? `, page ${citation.page_number}` : ""
  }`;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={label}
          onClick={() => {
            setOpen(false);
            onActivate(citation);
          }}
          onMouseEnter={() => setOpen(true)}
          onMouseLeave={() => setOpen(false)}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          className={cn(
            "cite-badge ml-0.5 inline-flex h-[1.1em] min-w-[1.1em] items-center justify-center",
            "rounded px-1 align-baseline text-[10px] font-semibold leading-none tabular-nums",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent",
            active
              ? "bg-accent text-accent-foreground"
              : "bg-accent/15 text-accent hover:bg-accent/25",
          )}
        >
          {n}
        </button>
      </PopoverTrigger>
      <PopoverContent
        side="top"
        align="start"
        className="w-[min(100vw-2rem,320px)] p-3"
        onOpenAutoFocus={(e) => e.preventDefault()}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
      >
        <p className="text-xs font-semibold text-text-primary">Source {n}</p>
        <p className="mt-0.5 text-xs text-text-secondary">
          {citation.title}
          {citation.page_number != null ? ` · Page ${citation.page_number}` : ""}
        </p>
        {citation.quote && (
          <p className="mt-2 line-clamp-5 text-[13px] leading-snug text-text-secondary">
            &ldquo;{citation.quote}&rdquo;
          </p>
        )}
        <button
          type="button"
          className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-accent hover:underline"
          onClick={() => {
            setOpen(false);
            onActivate(citation);
          }}
        >
          View in document
          <ExternalLink className="h-3 w-3" />
        </button>
      </PopoverContent>
    </Popover>
  );
}

interface SourcesDrawerProps {
  citations: AskCitationSnapshot[] | Citation[];
  activeNumber?: number | null;
  onOpen: (citation: Citation) => void;
  defaultOpen?: boolean;
}

export function SourcesDrawer({
  citations,
  activeNumber,
  onOpen,
  defaultOpen = false,
}: SourcesDrawerProps) {
  const [open, setOpen] = useState(defaultOpen);
  if (citations.length === 0) return null;

  return (
    <div className="mt-3">
      <button
        type="button"
        className="inline-flex items-center gap-1.5 text-xs font-medium text-text-muted hover:text-text-secondary"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden className="text-[10px]">
          {open ? "▾" : "▸"}
        </span>
        <span>
          {citations.length} source{citations.length === 1 ? "" : "s"}
        </span>
      </button>
      {open && (
        <ul className="mt-2 space-y-2 border-l-2 border-surface-border pl-3">
          {citations.map((raw, i) => {
            const c = toCitation(raw);
            const n = c.display_number ?? i + 1;
            return (
              <li key={`${c.chunk_id}-${n}`}>
                <button
                  type="button"
                  onClick={() => onOpen({ ...c, display_number: n })}
                  className={cn(
                    "group flex w-full gap-2 rounded-md py-1 text-left",
                    activeNumber === n && "bg-accent/5",
                  )}
                >
                  <span
                    className={cn(
                      "mt-0.5 flex h-5 min-w-5 items-center justify-center rounded text-[11px] font-semibold",
                      activeNumber === n
                        ? "bg-accent text-accent-foreground"
                        : "bg-accent/15 text-accent",
                    )}
                  >
                    {n}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[13px] font-medium text-text-primary">
                      {c.title}
                      {c.page_number != null ? ` · Page ${c.page_number}` : ""}
                    </span>
                    {c.quote && (
                      <span className="mt-0.5 line-clamp-2 block text-xs text-text-secondary">
                        &ldquo;{c.quote}&rdquo;
                      </span>
                    )}
                  </span>
                  <span className="shrink-0 self-center text-[11px] font-medium text-accent opacity-0 group-hover:opacity-100">
                    View
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export interface MarkdownResponseProps {
  content: string;
  citations: AskCitationSnapshot[] | Citation[];
  activeNumber?: number | null;
  onActivate: (citation: Citation) => void;
  className?: string;
}

/** Safe Markdown renderer for assistant answers; citations come only from validated metadata. */
export function MarkdownResponse({
  content,
  citations,
  activeNumber,
  onActivate,
  className,
}: MarkdownResponseProps) {
  const byNumber = new Map<number, Citation>();
  for (const raw of citations) {
    const c = toCitation(raw);
    const n = c.display_number;
    if (n != null) byNumber.set(n, c);
  }

  // Defense in depth: rewrite/strip raw chunk markers from older persisted messages.
  const safeContent = rewriteChunkMarkersForDisplay(content, citations);

  const withCitations = (children: ReactNode) =>
    injectCitations(children, byNumber, activeNumber, onActivate);

  return (
    <div
      className={cn(
        "ask-md text-[14px] leading-[1.6] text-text-primary break-words",
        className,
      )}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => (
            <p className="mb-2.5 last:mb-0">{withCitations(children)}</p>
          ),
          h1: ({ children }) => (
            <h3 className="mb-1.5 mt-3 text-[14px] font-semibold leading-snug first:mt-0">
              {withCitations(children)}
            </h3>
          ),
          h2: ({ children }) => (
            <h3 className="mb-1.5 mt-3 text-[14px] font-semibold leading-snug first:mt-0">
              {withCitations(children)}
            </h3>
          ),
          h3: ({ children }) => (
            <h4 className="mb-1 mt-2.5 text-[13.5px] font-semibold leading-snug first:mt-0">
              {withCitations(children)}
            </h4>
          ),
          h4: ({ children }) => (
            <h4 className="mb-1 mt-2 text-[13px] font-semibold leading-snug first:mt-0">
              {withCitations(children)}
            </h4>
          ),
          h5: ({ children }) => (
            <h5 className="mb-1 mt-2 text-[13px] font-semibold first:mt-0">
              {withCitations(children)}
            </h5>
          ),
          h6: ({ children }) => (
            <h6 className="mb-1 mt-2 text-[12.5px] font-semibold first:mt-0">
              {withCitations(children)}
            </h6>
          ),
          ul: ({ children }) => (
            <ul className="mb-2.5 list-disc space-y-1 pl-4 last:mb-0">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="mb-2.5 list-decimal space-y-1 pl-4 last:mb-0">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="pl-0.5 leading-[1.55]">{withCitations(children)}</li>
          ),
          strong: ({ children }) => (
            <strong className="font-semibold text-text-primary">
              {withCitations(children)}
            </strong>
          ),
          em: ({ children }) => <em className="italic">{withCitations(children)}</em>,
          blockquote: ({ children }) => (
            <blockquote className="mb-2.5 border-l-2 border-surface-border pl-3 text-text-secondary">
              {children}
            </blockquote>
          ),
          a: ({ href, children }) => {
            const safeHref = typeof href === "string" ? href : undefined;
            const external =
              !!safeHref &&
              (safeHref.startsWith("http://") || safeHref.startsWith("https://"));
            return (
              <a
                href={safeHref}
                className="text-accent underline-offset-2 hover:underline"
                {...(external
                  ? { target: "_blank", rel: "noopener noreferrer" }
                  : {})}
              >
                {withCitations(children)}
              </a>
            );
          },
          code: ({ className: codeClass, children }) => {
            const isBlock = typeof codeClass === "string" && codeClass.includes("language-");
            if (isBlock) {
              return (
                <code className={cn("font-mono text-[12.5px]", codeClass)}>{children}</code>
              );
            }
            return (
              <code className="rounded bg-surface-muted px-1 py-0.5 font-mono text-[12.5px]">
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="mb-2.5 overflow-x-auto rounded-md bg-surface-muted p-2.5 text-[12.5px] last:mb-0">
              {children}
            </pre>
          ),
          table: ({ children }) => (
            <div className="mb-2.5 overflow-x-auto last:mb-0">
              <table className="w-full border-collapse text-left text-[13px]">{children}</table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-b border-surface-border px-2 py-1 font-semibold">
              {withCitations(children)}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-b border-surface-border/60 px-2 py-1 align-top">
              {withCitations(children)}
            </td>
          ),
          hr: () => <hr className="my-3 border-surface-border" />,
        }}
      >
        {safeContent}
      </ReactMarkdown>
    </div>
  );
}

/** @deprecated Prefer MarkdownResponse */
export const AnswerBody = MarkdownResponse;
