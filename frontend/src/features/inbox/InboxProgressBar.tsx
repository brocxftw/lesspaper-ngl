import { cn } from "@/lib/utils";

interface InboxProgressBarProps {
  percent: number | null;
  className?: string;
}

export function InboxProgressBar({ percent, className }: InboxProgressBarProps) {
  const determinate = percent != null;
  const width = determinate ? Math.min(100, Math.max(0, percent)) : null;

  return (
    <div
      className={cn("h-1.5 w-full overflow-hidden rounded-full bg-[#E6EEF2]", className)}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={width ?? undefined}
    >
      <div
        className={cn(
          "h-full rounded-full bg-accent",
          determinate ? "transition-[width] duration-300" : "w-1/3 animate-pulse",
        )}
        style={width != null ? { width: `${width}%` } : undefined}
      />
    </div>
  );
}
