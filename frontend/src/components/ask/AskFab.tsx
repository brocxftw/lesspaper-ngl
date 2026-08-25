import { cn } from "@/lib/utils";
import { BrandMark } from "@/components/brand/BrandMark";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/Tooltip";

interface AskFabProps {
  onClick: () => void;
  className?: string;
}

/** Round Ask AI control used in document preview and the global dock. */
export function AskFab({ onClick, className }: AskFabProps) {
  return (
    <Tooltip delayDuration={200}>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label="Ask AI"
          onClick={onClick}
          className={cn(
            "flex h-12 w-12 items-center justify-center",
            "rounded-full bg-accent text-accent-foreground shadow-md",
            "transition hover:bg-accent-hover hover:shadow-lg",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus focus-visible:ring-offset-2",
            className,
          )}
        >
          <BrandMark variant="on-light" size={22} />
        </button>
      </TooltipTrigger>
      <TooltipContent side="left">Ask AI</TooltipContent>
    </Tooltip>
  );
}
