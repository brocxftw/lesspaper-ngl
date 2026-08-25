import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useAIHealth, useJobs, useSession } from "@/lib/api/hooks";
import type { AICapabilityHealth, AICapabilityStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/Tooltip";

type PipelineKey = "ocr" | "indexing" | "embedding" | "chat";

const PIPELINE_ROWS: { key: PipelineKey; label: string }[] = [
  { key: "ocr", label: "OCR" },
  { key: "indexing", label: "Indexing" },
  { key: "embedding", label: "Embedding" },
  { key: "chat", label: "Chat" },
];

/** Background jobs that mean the AI / ingest pipeline is actively working. */
const AI_ACTIVE_JOB_TYPES = new Set([
  "ocr",
  "metadata_suggestion",
  "embedding",
  "indexing",
  "summary",
]);

function capabilityReady(status: AICapabilityStatus | undefined): boolean {
  return status === "available";
}

function capabilityLabel(cap: AICapabilityHealth | undefined): string {
  if (!cap) return "Checking…";
  if (cap.status === "not_configured") return "Not configured";
  if (cap.status === "checking") return "Checking…";
  if (cap.status === "unavailable") return cap.error?.trim() || "Unavailable";
  return cap.model?.trim() || cap.provider || "Available";
}

function StatusDot({
  working,
  ready,
  checking,
  size = "sm",
}: {
  working: boolean;
  ready: boolean;
  checking?: boolean;
  size?: "sm" | "md";
}) {
  return (
    <span
      className={cn(
        "shrink-0 rounded-full",
        size === "md" ? "h-2.5 w-2.5" : "h-2 w-2",
        working || checking
          ? "animate-pulse bg-amber-400"
            : ready
            ? "bg-emerald-500"
            : "bg-navbar-muted",
      )}
    />
  );
}

/** Compact AI status for the top navbar. Details appear on hover. */
export function AiStatusPill() {
  const navigate = useNavigate();
  const { data: session } = useSession();
  const isAdmin = Boolean(session?.user.is_admin);
  const { data: aiHealth } = useAIHealth();
  const { data: runningJobs = [] } = useJobs("running");
  const { data: queuedJobs = [] } = useJobs("queued");

  const pipelineRows = PIPELINE_ROWS.map(({ key, label }) => {
    const cap = aiHealth?.[key];
    return {
      key,
      label,
      detail: capabilityLabel(cap),
      ready: capabilityReady(cap?.status),
      checking: cap?.status === "checking",
      notConfigured: cap?.status === "not_configured",
    };
  });

  const aiWorking = useMemo(() => {
    const jobs = [...runningJobs, ...queuedJobs];
    return jobs.some((j) => AI_ACTIVE_JOB_TYPES.has(j.job_type));
  }, [runningJobs, queuedJobs]);

  const roleWorking = useMemo(() => {
    const jobs = [...runningJobs, ...queuedJobs];
    const types = new Set(jobs.map((j) => j.job_type));
    return {
      ocr: types.has("ocr"),
      indexing:
        types.has("metadata_suggestion") ||
        types.has("summary") ||
        types.has("indexing"),
      embedding: types.has("embedding"),
      chat: false,
    };
  }, [runningJobs, queuedJobs]);

  const configuredRows = pipelineRows.filter((r) => !r.notConfigured);
  const allConfiguredReady =
    configuredRows.length > 0 && configuredRows.every((r) => r.ready);
  const settingsPath = isAdmin
    ? "/settings/artificial-intelligence"
    : "/settings/about";

  const tooltipRows = pipelineRows
    .filter((row) => row.key !== "ocr")
    .map((row) => ({
      key: row.key,
      label: row.label,
      value: row.detail,
      working: roleWorking[row.key],
      ready: row.ready,
      checking: row.checking,
    }));

  return (
    <Tooltip delayDuration={200}>
      <TooltipTrigger asChild>
        <button
          type="button"
          data-tour="ai"
          className={cn(
            "inline-flex h-[41px] items-center gap-2 rounded-md px-1.5",
            "text-[#F8FAFC] transition-opacity duration-150 ease-out hover:opacity-80",
          )}
          aria-label="Open AI settings"
          onClick={() => navigate(settingsPath)}
        >
          <StatusDot
            working={aiWorking}
            ready={allConfiguredReady}
            checking={!aiHealth}
            size="md"
          />
          <span className="text-sm font-semibold">AI</span>
        </button>
      </TooltipTrigger>
      <TooltipContent
        side="bottom"
        align="end"
        sideOffset={8}
        className="w-72 rounded-xl border border-surface-border bg-surface p-3.5 text-text-primary shadow-[0_10px_30px_rgba(15,23,42,0.14)]"
      >
        <ul className="space-y-2">
          {tooltipRows.map((row) => (
            <li key={row.key} className="flex items-center gap-2 text-[13px] leading-snug">
              <StatusDot
                working={row.working}
                ready={row.ready}
                checking={row.checking}
              />
              <span className="w-[72px] shrink-0 font-medium text-text-secondary">
                {row.label}
              </span>
              <span className="min-w-0 flex-1 truncate text-text-primary" title={row.value}>
                {row.value}
              </span>
            </li>
          ))}
        </ul>
      </TooltipContent>
    </Tooltip>
  );
}
