import {
  Clock,
  FileCheck2,
  FileWarning,
  Rocket,
  Sparkles,
} from "lucide-react";
import type { OverviewMetrics } from "./inboxPresentation";
import { cn } from "@/lib/utils";

interface InboxOverviewMetricsProps {
  metrics: OverviewMetrics;
}

const ICON_TONE = "text-[#64748B]";
const ICON_CHIP = "bg-[#F1F5F9]";

const CARDS: {
  id: keyof OverviewMetrics;
  label: string;
  icon: typeof FileCheck2;
  format: (m: OverviewMetrics) => string;
}[] = [
  {
    id: "processed",
    label: "Processed",
    icon: FileCheck2,
    format: (m) => m.processed.toLocaleString(),
  },
  {
    id: "failed",
    label: "Failed",
    icon: FileWarning,
    format: (m) => m.failed.toLocaleString(),
  },
  {
    id: "processing",
    label: "Processing",
    icon: Clock,
    format: (m) => m.processing.toLocaleString(),
  },
  {
    id: "totalIngested",
    label: "Total ingested",
    icon: Sparkles,
    format: (m) => m.totalIngested.toLocaleString(),
  },
  {
    id: "successRate",
    label: "Success rate",
    icon: Rocket,
    format: (m) => (m.successRate == null ? "—" : `${m.successRate.toFixed(1)}%`),
  },
];

export function InboxOverviewMetrics({ metrics }: InboxOverviewMetricsProps) {
  const successRate = metrics.successRate == null ? "—" : `${metrics.successRate.toFixed(1)}%`;
  return (
    <section className="mt-6 md:mt-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-base font-bold text-[#14212B]">Overview</h2>
        <p className="text-[11px] text-[#64748B]"><span className="md:hidden">Since last reset</span><span className="hidden md:inline">Historical counters since last reset</span></p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        {CARDS.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.id}
              className={cn(
                "min-h-[74px] rounded-[10px] border border-[#E1E7EB] bg-white p-3 shadow-[0_1px_2px_rgba(20,33,43,0.03)] md:min-h-[90px] md:rounded-[9px] md:p-3.5",
                card.id === "successRate" && "hidden md:block",
              )}
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-[11px] font-medium text-[#5D6B76]">{card.label}</p>
                  <p className="mt-0.5 text-xl font-bold tracking-tight text-[#14212B] md:mt-1 md:text-2xl">
                    {card.format(metrics)}
                  </p>
                </div>
                <div
                  className={cn(
                    "flex h-8 w-8 items-center justify-center rounded-[8px] md:h-[42px] md:w-[42px] md:rounded-[10px]",
                    ICON_CHIP,
                    ICON_TONE,
                  )}
                >
                  <Icon className="h-4 w-4 md:h-[22px] md:w-[22px]" strokeWidth={1.75} />
                </div>
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-3 rounded-[10px] border border-[#E1E7EB] bg-white p-3 md:hidden">
        <div className="flex items-center justify-between gap-3 text-sm font-semibold text-[#14212B]">
          <span>Success rate</span>
          <span>{successRate}</span>
        </div>
        <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-accent-muted" aria-label={`Success rate ${successRate}`}>
          <div className="h-full rounded-full bg-accent" style={{ width: `${Math.max(0, Math.min(metrics.successRate ?? 0, 100))}%` }} />
        </div>
      </div>
    </section>
  );
}
