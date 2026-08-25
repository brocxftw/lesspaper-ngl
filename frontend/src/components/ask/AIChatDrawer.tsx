import {
  AIChatPanel,
  type AIDrawerScope,
} from "@/components/ask/AIChatPanel";
import type { Citation } from "@/lib/api/types";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/Sheet";
import { Sparkles } from "lucide-react";

export type { AIDrawerScope, AIDrawerScopeKind } from "@/components/ask/AIChatPanel";

interface AIChatDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initialScope?: AIDrawerScope;
  onCitationClick: (citation: Citation) => void;
}

/** Page-level Ask drawer (full-height Sheet). Preview modal uses AIChatPanel instead. */
export function AIChatDrawer({
  open,
  onOpenChange,
  initialScope,
  onCitationClick,
}: AIChatDrawerProps) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full p-0 sm:max-w-md">
        <SheetHeader className="sr-only">
          <SheetTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-text-muted" />
            Ask AI
          </SheetTitle>
          <SheetDescription>
            Single-turn answers with citations from the selected scope.
          </SheetDescription>
        </SheetHeader>
        <AIChatPanel
          active={open}
          initialScope={initialScope}
          onCitationClick={onCitationClick}
          className="h-full"
        />
      </SheetContent>
    </Sheet>
  );
}
