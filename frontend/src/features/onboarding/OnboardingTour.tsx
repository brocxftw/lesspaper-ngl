import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { BrandMark } from "@/components/brand/BrandMark";
import { Button } from "@/components/ui/Button";
import { useCompleteOnboarding, useOnboardingStatus } from "@/lib/api/hooks";

type Mode = "closed" | "welcome" | "tour";

const TOUR_STEPS = [
  { id: "inbox", path: "/inbox", title: "Inbox", description: "New documents arrive here first, ready for review and processing. You can drag and drop folders and documents here for processing." },
  { id: "upload", path: "/inbox?view=work", title: "Upload", description: "lesspaper supports folders, PDF, PNG, JPEG, text, Markdown, and DOCX files." },
  { id: "library", path: "/documents", title: "Library", description: "Your processed documents live here, organised and ready to find." },
  { id: "trash", path: "/trash", title: "Trash", description: "Deleted documents are kept here for 30 days before they are automatically deleted." },
  { id: "search", path: "/search", title: "Search", description: "Search uses fuzzy matching and shows relevant files as you type." },
  { id: "settings", path: "/settings/profile", title: "Settings", description: "Manage your account and app settings here." },
  { id: "ai", path: "/settings/artificial-intelligence", title: "AI", description: "AI is optional. Configure providers and controls here whenever you are ready." },
] as const;

type TourContextValue = { replay: () => void };
const TourContext = createContext<TourContextValue | null>(null);

export function useOnboardingTour() {
  const context = useContext(TourContext);
  return context ?? { replay: () => undefined };
}

export function OnboardingTourProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const status = useOnboardingStatus();
  const complete = useCompleteOnboarding();
  const [mode, setMode] = useState<Mode>("closed");
  const [stepIndex, setStepIndex] = useState(0);
  const [replaying, setReplaying] = useState(false);
  const restoreFocus = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (status.data?.required && mode === "closed") setMode("welcome");
  }, [status.data?.required, mode]);

  useEffect(() => {
    if (mode === "tour") navigate(TOUR_STEPS[stepIndex].path);
  }, [mode, navigate, stepIndex]);

  const close = useCallback(async (persist: boolean) => {
    if (persist && !replaying) await complete.mutateAsync();
    setMode("closed");
    setReplaying(false);
    restoreFocus.current?.focus();
  }, [complete, replaying]);

  const finish = useCallback(async () => {
    await close(true);
    navigate("/inbox");
  }, [close, navigate]);

  const replay = useCallback(() => {
    restoreFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    setReplaying(true);
    setStepIndex(0);
    setMode("welcome");
  }, []);

  return (
    <TourContext.Provider value={{ replay }}>
      {children}
      {mode !== "closed" && (
        <TourOverlay
          mode={mode}
          stepIndex={stepIndex}
          busy={complete.isPending}
          onBegin={() => { setStepIndex(0); setMode("tour"); }}
          onBack={() => {
            setStepIndex((index) => Math.max(0, index - 1));
          }}
          onNext={() => setStepIndex((index) => index + 1)}
          onSkip={() => void close(true)}
          onFinish={() => void finish()}
        />
      )}
    </TourContext.Provider>
  );
}

function TourOverlay({
  mode, stepIndex, busy, onBegin, onBack, onNext, onSkip, onFinish,
}: {
  mode: Mode; stepIndex: number; busy: boolean; onBegin: () => void; onBack: () => void;
  onNext: () => void; onSkip: () => void; onFinish: () => void;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const step = TOUR_STEPS[stepIndex];
  const [rect, setRect] = useState<DOMRect | null>(null);

  useEffect(() => {
    cardRef.current?.focus();
  }, [mode, stepIndex]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); onSkip(); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onSkip]);

  useLayoutEffect(() => {
    if (mode !== "tour") return;
    const update = () => {
      const target = document.querySelector<HTMLElement>(`[data-tour="${step.id}"]`);
      if (target && typeof target.scrollIntoView === "function") {
        target.scrollIntoView({ block: "nearest", inline: "nearest" });
      }
      setRect(target?.getBoundingClientRect() ?? null);
    };
    update();
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => { window.removeEventListener("resize", update); window.removeEventListener("scroll", update, true); };
  }, [mode, step.id]);

  if (typeof document === "undefined") return null;
  const centered = mode !== "tour";
  const top = rect ? Math.min(window.innerHeight - 220, Math.max(16, rect.bottom + 16)) : 96;
  const left = rect ? Math.min(window.innerWidth - 340, Math.max(16, rect.left)) : 16;

  return createPortal(
    <div className="fixed inset-0 z-[100]" aria-live="polite">
      <div className="absolute inset-0 bg-slate-950/40" aria-hidden="true" />
      {mode === "tour" && rect && <div aria-hidden="true" className="pointer-events-none fixed rounded-lg ring-4 ring-accent shadow-[0_0_0_9999px_rgba(15,23,42,0.12)]" style={{ top: rect.top - 4, left: rect.left - 4, width: rect.width + 8, height: rect.height + 8 }} />}
      <div
        ref={cardRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-title"
        tabIndex={-1}
        style={centered ? undefined : { top, left }}
        className={centered ? "absolute left-1/2 top-1/2 w-[min(92vw,380px)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-surface-border bg-surface p-6 shadow-xl outline-none" : "absolute w-[min(92vw,340px)] rounded-xl border border-surface-border bg-surface p-5 shadow-xl outline-none"}
      >
        {mode === "welcome" && <><div className="flex justify-center"><BrandMark variant="on-light" size={42} /></div><h2 id="tour-title" className="mt-4 text-center text-xl font-semibold">Welcome to lesspaper-ngl</h2><p className="mt-2 text-center text-sm text-text-secondary">Here’s a quick look around. It’ll only take a moment.</p><div className="mt-6 flex justify-between"><Button variant="ghost" onClick={onSkip} disabled={busy}>Skip</Button><Button onClick={onBegin}>Next</Button></div></>}
        {mode === "tour" && <><p className="text-xs font-medium text-accent">{stepIndex + 1} / {TOUR_STEPS.length}</p><h2 id="tour-title" className="mt-1 text-lg font-semibold">{step.title}</h2><p className="mt-2 text-sm text-text-secondary">{step.description}</p><div className="mt-5 flex items-center justify-between gap-2"><Button variant="ghost" onClick={onBack} disabled={stepIndex === 0}>Back</Button><div className="flex gap-2"><Button variant="ghost" onClick={onSkip} disabled={busy}>Skip</Button><Button onClick={stepIndex === TOUR_STEPS.length - 1 ? onFinish : onNext} disabled={busy}>{stepIndex === TOUR_STEPS.length - 1 ? "Finish" : "Next"}</Button></div></div></>}
      </div>
    </div>, document.body,
  );
}
