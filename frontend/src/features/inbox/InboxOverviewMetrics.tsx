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
  return (
    <section className="mt-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h2 className="text-base font-bold text-[#14212B]">Overview</h2>
        <p className="text-[11px] text-[#64748B]">Historical counters since last reset</p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 md:grid-cols-3 xl:grid-cols-5">
        {CARDS.map((card) => {
          const Icon = card.icon;
          return (
            <div
              key={card.id}
              className="min-h-[90px] rounded-[9px] border border-[#E1E7EB] bg-white p-3.5 shadow-[0_1px_2px_rgba(20,33,43,0.03)]"
            >
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-[11px] font-medium text-[#5D6B76]">{card.label}</p>
                  <p className="mt-1 text-2xl font-bold tracking-tight text-[#14212B]">
                    {card.format(metrics)}
                  </p>
                </div>
                <div
                  className={cn(
                    "flex h-[42px] w-[42px] items-center justify-center rounded-[10px]",
                    ICON_CHIP,
                    ICON_TONE,
                  )}
                >
                  <Icon className="h-[22px] w-[22px]" strokeWidth={1.75} />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
