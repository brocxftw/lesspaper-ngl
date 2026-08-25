import { cn } from "@/lib/utils";

export function AiProfileOption({
  label,
  tagline,
  spec,
  selected,
  onSelect,
}: {
  label: string;
  tagline: string;
  spec: string;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full items-start gap-3 rounded-lg border px-4 py-3 text-left transition-colors",
        selected
          ? "border-accent bg-accent-muted/20 ring-1 ring-accent/30"
          : "border-surface-border bg-surface hover:border-accent/40 hover:bg-surface-muted/50",
      )}
    >
      <span
        className={cn(
          "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2",
          selected ? "border-accent bg-accent" : "border-surface-border bg-surface",
        )}
        aria-hidden
      >
        {selected && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium text-text-primary">{label}</span>
          <span className="text-xs text-text-muted">{tagline}</span>
        </span>
        <span className="mt-0.5 block text-xs text-text-secondary">{spec}</span>
      </span>
    </button>
  );
}
