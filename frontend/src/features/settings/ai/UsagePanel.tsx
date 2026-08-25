import { useMemo, useState } from "react";
import { Activity, Clock, Coins, FileText, Layers, MessageCircleQuestion } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useAIUsage } from "@/lib/api/hooks";
import type { AIUsageSummary } from "@/lib/api/types";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import { AiBreakdownPanel } from "./AiBreakdownPanel";
import { SettingsCard, SettingsEmptyState, SettingsMetricCard } from "@/features/settings/components";
import { workloadDisplayLabel } from "./workloadCopy";

type UsageRange = "today" | "7d" | "30d" | "month";
type UsageInterval = AIUsageSummary["interval"];
type UsagePoint = { bucket: string; requests: number };

function formatCount(value: number): string {
  if (value < 1_000) return value.toLocaleString();

  const suffixes = ["", "k", "M", "B"];
  const magnitude = Math.min(Math.floor(Math.log10(value) / 3), suffixes.length - 1);
  const scaled = value / 10 ** (magnitude * 3);
  return `${scaled >= 10 ? scaled.toFixed(0) : scaled.toFixed(1).replace(/\.0$/, "")}${suffixes[magnitude]}`;
}

function createCountTicks(maxValue: number): { yMax: number; values: number[] } {
  const targetIntervals = 4;
  const rawInterval = maxValue / targetIntervals;
  const magnitude = 10 ** Math.floor(Math.log10(rawInterval));
  const normalized = rawInterval / magnitude;
  const interval = Math.max(
    1,
    (normalized <= 1 ? 1 : normalized <= 2 ? 2 : normalized <= 5 ? 5 : 10) * magnitude,
  );
  const yMax = Math.ceil(maxValue / interval) * interval;
  const intervals = Math.round(yMax / interval);

  return {
    yMax,
    values: Array.from({ length: intervals + 1 }, (_, index) => yMax - index * interval),
  };
}

function selectTickIndexes(length: number, maxTicks: number): number[] {
  if (length <= maxTicks) return Array.from({ length }, (_, index) => index);

  return Array.from({ length: maxTicks }, (_, index) =>
    Math.round((index * (length - 1)) / (maxTicks - 1)),
  );
}

function formatBucketLabel(bucket: string, interval: UsageInterval): string {
  const date = new Date(bucket);
  return new Intl.DateTimeFormat(
    "en-GB",
    interval === "hour"
      ? { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone: "UTC" }
      : { day: "2-digit", month: "short", timeZone: "UTC" },
  ).format(date);
}

function formatBucketTooltip(bucket: string): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "UTC",
  }).formatToParts(new Date(bucket));
  const value = (type: Intl.DateTimeFormatPartTypes) => parts.find((part) => part.type === type)?.value;

  return `${value("day")} ${value("month")} ${value("year")}, ${value("hour")}:${value("minute")} UTC`;
}

function UsageAreaChart({ points, interval }: { points: UsagePoint[]; interval: UsageInterval }) {
  const [hoveredPoint, setHoveredPoint] = useState<(UsagePoint & { x: number; y: number }) | null>(null);
  const max = Math.max(1, ...points.map((point) => point.requests));
  const { yMax, values: yTickValues } = createCountTicks(max);
  const width = 800;
  const height = 220;
  const padding = { top: 16, bottom: 48, left: 52, right: 14 };
  const chartW = width - padding.left - padding.right;
  const chartH = height - padding.top - padding.bottom;
  const xTickIndexes = selectTickIndexes(points.length, interval === "hour" ? 5 : 6);

  const coords = points.map((point, index) => {
    const x =
      points.length <= 1
        ? padding.left + chartW / 2
        : padding.left + (index / (points.length - 1)) * chartW;
    const y =
      padding.top + chartH - (point.requests / yMax) * chartH;
    return { x, y, ...point };
  });

  const linePath = coords
    .map((point, index) => `${index ? "L" : "M"} ${point.x} ${point.y}`)
    .join(" ");
  const areaPath =
    coords.length > 0
      ? `${linePath} L ${coords[coords.length - 1].x} ${padding.top + chartH} L ${coords[0].x} ${padding.top + chartH} Z`
      : "";
  const tooltipWidth = 180;
  const tooltipHeight = 44;
  const tooltip = hoveredPoint && {
    x: Math.min(Math.max(hoveredPoint.x + 10, padding.left), width - padding.right - tooltipWidth),
    y:
      hoveredPoint.y < padding.top + tooltipHeight + 8
        ? hoveredPoint.y + 10
        : hoveredPoint.y - tooltipHeight - 10,
  };

  return (
    <SettingsCard padding="sm">
      <h3 className="text-sm font-semibold text-text-primary">Requests over time</h3>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="mt-3 h-52 w-full"
        role="img"
        aria-labelledby="usage-chart-title"
        aria-describedby="usage-chart-data"
      >
        <title id="usage-chart-title">AI requests over time</title>
        <text
          x="14"
          y={padding.top + chartH / 2}
          textAnchor="middle"
          fill="var(--color-text-muted)"
          fontSize="10"
          transform={`rotate(-90 14 ${padding.top + chartH / 2})`}
          data-testid="usage-chart-y-axis-label"
        >
          Requests
        </text>
        <text
          x={width / 2}
          y={height - 5}
          textAnchor="middle"
          fill="var(--color-text-muted)"
          fontSize="10"
          data-testid="usage-chart-x-axis-label"
        >
          Time (UTC)
        </text>
        {yTickValues.map((value, index) => {
          const y = padding.top + chartH - (value / yMax) * chartH;
          return (
            <g key={`${value}-${index}`}>
              <line
                x1={padding.left}
                x2={width - padding.right}
                y1={y}
                y2={y}
                stroke="var(--color-surface-border)"
                strokeWidth="1"
              />
              <text
                x={padding.left - 8}
                y={y + 3.5}
                textAnchor="end"
                fill="var(--color-text-muted)"
                fontSize="10"
                data-testid="usage-chart-y-tick"
              >
                {formatCount(value)}
              </text>
            </g>
          );
        })}
        {xTickIndexes.map((index) => {
          const point = coords[index];
          return (
            <text
              key={point.bucket}
              x={point.x}
              y={padding.top + chartH + 17}
              textAnchor="middle"
              fill="var(--color-text-muted)"
              fontSize="10"
              data-testid="usage-chart-x-tick"
            >
              {formatBucketLabel(point.bucket, interval)}
            </text>
          );
        })}
        {areaPath && (
          <path d={areaPath} fill="var(--color-accent-muted)" fillOpacity="0.45" />
        )}
        {linePath && (
          <path d={linePath} fill="none" stroke="var(--color-accent)" strokeWidth="2.5" />
        )}
        {coords.map((point) => (
          <g
            key={point.bucket}
            tabIndex={0}
            aria-label={`${formatBucketTooltip(point.bucket)}: ${point.requests} requests`}
            onMouseEnter={() => setHoveredPoint(point)}
            onMouseLeave={() => setHoveredPoint(null)}
            onFocus={() => setHoveredPoint(point)}
            onBlur={() => setHoveredPoint(null)}
          >
            <circle cx={point.x} cy={point.y} r="10" fill="transparent" />
            <circle
              cx={point.x}
              cy={point.y}
              r="3.5"
              fill="var(--color-accent)"
              data-testid="usage-chart-point"
            />
          </g>
        ))}
        {tooltip && hoveredPoint && (
          <g pointerEvents="none" data-testid="usage-chart-tooltip">
            <rect
              x={tooltip.x}
              y={tooltip.y}
              width={tooltipWidth}
              height={tooltipHeight}
              rx="4"
              fill="var(--color-surface)"
              stroke="var(--color-surface-border)"
            />
            <text x={tooltip.x + 10} y={tooltip.y + 17} fill="var(--color-text-primary)" fontSize="10">
              {formatBucketTooltip(hoveredPoint.bucket)}
            </text>
            <text x={tooltip.x + 10} y={tooltip.y + 33} fill="var(--color-text-secondary)" fontSize="10">
              Requests: {hoveredPoint.requests.toLocaleString()}
            </text>
          </g>
        )}
      </svg>
      <ul id="usage-chart-data" className="sr-only" aria-label="AI requests data">
        {points.map((point) => (
          <li key={point.bucket}>
            {formatBucketTooltip(point.bucket)}: {point.requests.toLocaleString()} requests
          </li>
        ))}
      </ul>
    </SettingsCard>
  );
}

function formatDuration(ms: number): string {
  if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)} ms`;
}

function PerformanceCard({
  title,
  avgLabel,
  avgValue,
  countLabel,
  countValue,
  icon: Icon,
}: {
  title: string;
  avgLabel: string;
  avgValue: string;
  countLabel: string;
  countValue: string;
  icon: LucideIcon;
}) {
  return (
    <SettingsCard padding="sm">
      <div className="flex gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-surface-muted text-text-muted">
          <Icon className="h-4 w-4" strokeWidth={1.75} aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <h4 className="text-sm font-semibold text-text-primary">{title}</h4>
          <dl className="mt-2 grid grid-cols-2 gap-3">
            <div className="flex flex-col">
              <dd className="text-lg font-bold leading-tight text-text-primary">{avgValue}</dd>
              <dt className="mt-1 text-xs text-text-muted">{avgLabel}</dt>
            </div>
            <div className="flex flex-col">
              <dd className="text-lg font-bold leading-tight text-text-primary">{countValue}</dd>
              <dt className="mt-1 text-xs text-text-muted">{countLabel}</dt>
            </div>
          </dl>
        </div>
      </div>
    </SettingsCard>
  );
}

export function UsagePanel() {
  const [range, setRange] = useState<UsageRange>("month");
  const { data, isLoading, error } = useAIUsage(range);

  const workloadMap = useMemo(() => {
    const map = new Map<string, { requests: number; duration_ms: number | null }>();
    for (const item of data?.by_workload ?? []) {
      map.set(item.key, {
        requests: item.requests,
        duration_ms: item.duration_ms ?? null,
      });
    }
    return map;
  }, [data?.by_workload]);

  if (isLoading) {
    return <p className="text-sm text-text-muted">Loading deployment usage…</p>;
  }
  if (error || !data) {
    return (
      <p role="alert" className="text-sm text-danger">
        Usage data is unavailable.
      </p>
    );
  }

  const totals = data.totals;
  const avgPerRequest =
    totals.duration_ms != null && totals.requests > 0
      ? formatDuration(totals.duration_ms / totals.requests)
      : null;

  const costPrimary =
    totals.cost_coverage === "local_only"
      ? "Unavailable"
      : totals.estimated_cost == null
        ? "Unavailable"
        : `${totals.estimated_cost.toFixed(4)} ${totals.cost_currency || ""}`.trim();

  const costSecondary =
    totals.cost_coverage === "local_only"
      ? "Local models"
      : totals.cost_coverage === "none"
        ? "No cost data recorded"
        : "Total tokens processed";

  const chat = workloadMap.get("chat");
  const indexing = workloadMap.get("indexing");
  const embeddings = workloadMap.get("embeddings");

  const chatAvg =
    chat?.duration_ms != null && chat.requests > 0
      ? formatDuration(chat.duration_ms / chat.requests)
      : "Unavailable";
  const filingAvg =
    indexing?.duration_ms != null && indexing.requests > 0
      ? formatDuration(indexing.duration_ms / indexing.requests)
      : "Unavailable";
  const embedAvg =
    embeddings?.duration_ms != null && embeddings.requests > 0
      ? formatDuration(embeddings.duration_ms / embeddings.requests)
      : "Unavailable";

  return (
    <section aria-labelledby="usage-heading" className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 id="usage-heading" className="sr-only">
            Usage
          </h2>
          <p className="text-sm text-text-secondary">All AI workloads · UTC</p>
        </div>
        <div className="flex items-center gap-2">
          <label htmlFor="usage-range" className="text-xs text-text-muted">
            Time range
          </label>
          <Select value={range} onValueChange={(value) => setRange(value as UsageRange)}>
            <SelectTrigger id="usage-range" className="w-36" aria-label="Usage range">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="today">Today</SelectItem>
              <SelectItem value="7d">7 days</SelectItem>
              <SelectItem value="30d">30 days</SelectItem>
              <SelectItem value="month">This month</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <SettingsMetricCard
          label="Requests"
          value={totals.requests.toLocaleString()}
          secondary="In selected period"
          icon={Activity}
        />
        <SettingsMetricCard
          label="Tokens"
          value={
            totals.input_tokens == null && totals.output_tokens == null
              ? "Unavailable"
              : `${(totals.input_tokens || 0).toLocaleString()} in · ${(totals.output_tokens || 0).toLocaleString()} out`
          }
          secondary="Total tokens processed"
          icon={Layers}
        />
        <SettingsMetricCard
          label="AI time"
          value={
            totals.duration_ms == null
              ? "Unavailable"
              : `${(totals.duration_ms / 1000).toLocaleString()} s`
          }
          secondary={avgPerRequest ? `avg ${avgPerRequest} / request` : "Processing time"}
          icon={Clock}
        />
        <SettingsMetricCard
          label="Estimated cost"
          value={costPrimary}
          secondary={costSecondary}
          icon={Coins}
        />
      </div>

      {totals.requests === 0 ? (
        <SettingsEmptyState bordered>
          No AI requests yet for this period. Document management continues to work without AI activity.
        </SettingsEmptyState>
      ) : (
        <UsageAreaChart points={data.time_series} interval={data.interval} />
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <AiBreakdownPanel
          title="Workload breakdown"
          values={data.by_workload}
          totalRequests={totals.requests}
        />
        <AiBreakdownPanel
          title="Provider breakdown"
          values={data.by_provider.map((p) => ({
            key: p.key,
            label: p.label,
            requests: p.requests,
          }))}
          totalRequests={totals.requests}
        />
      </div>

      <div>
        <h3 className="mb-3 text-sm font-semibold text-text-primary">Performance</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <PerformanceCard
            title={workloadDisplayLabel("chat")}
            avgLabel="Average"
            avgValue={chatAvg}
            countLabel="Requests"
            countValue={chat ? chat.requests.toLocaleString() : "0"}
            icon={MessageCircleQuestion}
          />
          <PerformanceCard
            title={workloadDisplayLabel("indexing")}
            avgLabel="Average"
            avgValue={filingAvg}
            countLabel="Completed"
            countValue={indexing ? indexing.requests.toLocaleString() : "0"}
            icon={FileText}
          />
          <PerformanceCard
            title={workloadDisplayLabel("embeddings")}
            avgLabel="Average"
            avgValue={embedAvg}
            countLabel="Requests"
            countValue={embeddings ? embeddings.requests.toLocaleString() : "0"}
            icon={Layers}
          />
        </div>
      </div>

      {totals.cost_coverage === "partial" && (
        <p className="text-xs text-warning">
          Cost coverage is partial; unknown remote costs are excluded.
        </p>
      )}
    </section>
  );
}
