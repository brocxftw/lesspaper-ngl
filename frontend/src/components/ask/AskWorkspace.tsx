import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  AIChatDrawer,
  type AIDrawerScope,
} from "@/components/ask/AIChatDrawer";
import { Button } from "@/components/ui/Button";
import { Sparkles } from "lucide-react";

/** Standalone Ask route — reuses the Documents AI drawer for parity. */
export function AskWorkspace() {
  const [params] = useSearchParams();
  const q = params.get("q")?.trim() ?? "";
  const [open, setOpen] = useState(true);

  const initialScope: AIDrawerScope = useMemo(() => {
    if (q) {
      return {
        kind: "search",
        search: { query: q, mode: "hybrid" },
        label: `Search: ${q}`,
      };
    }
    return { kind: "library" };
  }, [q]);

  useEffect(() => {
    setOpen(true);
  }, [q]);

  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 bg-surface-muted p-8">
      <div className="max-w-md text-center">
        <Sparkles className="mx-auto mb-3 h-10 w-10 text-text-muted/40" />
        <h1 className="text-lg font-semibold text-text-primary">Ask lesspaper-ngl</h1>
        <p className="mt-1 text-sm text-text-secondary">
          Open the Ask panel to question your library with citations. Prefer
          launching Ask from Documents so folder, selection, and search scopes
          are preserved.
        </p>
        <Button className="mt-4" onClick={() => setOpen(true)}>
          Open Ask
        </Button>
      </div>
      <AIChatDrawer
        open={open}
        onOpenChange={setOpen}
        initialScope={initialScope}
        onCitationClick={(citation) => {
          const next = new URLSearchParams();
          next.set("doc", citation.document_id);
          if (citation.page_number) {
            next.set("viewerPage", String(citation.page_number));
          }
          window.location.assign(`/documents?${next.toString()}`);
        }}
      />
    </div>
  );
}
