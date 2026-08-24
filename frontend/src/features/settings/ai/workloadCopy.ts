import type { AIWorkloadRole } from "@/lib/api/types";
import { FileText, Layers, MessageCircleQuestion, Eye } from "lucide-react";
import type { LucideIcon } from "lucide-react";

export const WORKLOAD_LABELS: Record<string, string> = {
  indexing: "Filing suggestions",
  chat: "Ask lesspaper-ngl",
  embeddings: "Embeddings",
  embedding: "Embeddings",
};

export function workloadDisplayLabel(key: string, fallback?: string): string {
  return WORKLOAD_LABELS[key] ?? fallback ?? key;
}

export const WORKLOAD_COPY: Record<
  AIWorkloadRole,
  { title: string; subtitle: string; icon: LucideIcon }
> = {
  indexing: {
    title: "Filing suggestions",
    subtitle: "Title, folder, tags, type and correspondent suggestions",
    icon: FileText,
  },
  embedding: {
    title: "Embeddings",
    subtitle: "Semantic and hybrid retrieval",
    icon: Layers,
  },
  chat: {
    title: "Ask lesspaper-ngl",
    subtitle: "Answers questions using retrieved evidence",
    icon: MessageCircleQuestion,
  },
  vision: {
    title: "Vision",
    subtitle: "Legacy/experimental assignment",
    icon: Eye,
  },
};

export const PRIVACY_MODE_COPY: Record<
  string,
  { label: string; helper: string }
> = {
  local_only: {
    label: "Local only",
    helper: "Only local AI providers may be used. Remote AI is blocked.",
  },
  private_hybrid: {
    label: "Private hybrid",
    helper: "Prefer local AI. Remote providers require your permission.",
  },
  standard: {
    label: "Standard",
    helper: "Remote AI is allowed when enabled below.",
  },
};

export const PROFILE_OPTIONS = [
  {
    id: "lightweight" as const,
    label: "Lightweight",
    tagline: "Fastest",
    spec: "3 chunks · 8k context · 2k output",
  },
  {
    id: "balanced" as const,
    label: "Balanced",
    tagline: "Recommended",
    spec: "8 chunks · 16k context · 3k output",
  },
  {
    id: "quality" as const,
    label: "Quality",
    tagline: "More evidence",
    spec: "16 chunks · 32k context · 4k output",
  },
  {
    id: "custom" as const,
    label: "Custom",
    tagline: "Manual tuning",
    spec: "User-defined limits",
  },
];

export type AiSettingsTab = "usage" | "models" | "controls";

export const AI_SETTINGS_TABS: AiSettingsTab[] = ["usage", "models", "controls"];

export const AI_TAB_LABELS: Record<AiSettingsTab, string> = {
  usage: "Usage",
  models: "Models",
  controls: "Controls",
};

export const AI_TAB_DESCRIPTIONS: Record<AiSettingsTab, string> = {
  usage: "Monitor usage, performance and cost across lesspaper-ngl AI workloads.",
  models: "Configure which models lesspaper-ngl uses for each AI workload.",
  controls: "Control privacy, automated AI behaviour and response quality.",
};

export const LEGACY_TAB_ALIASES: Record<string, AiSettingsTab> = {
  providers: "models",
  policy: "controls",
  advanced: "controls",
};

export function resolveAiSettingsTab(raw: string | null): AiSettingsTab {
  if (raw && AI_SETTINGS_TABS.includes(raw as AiSettingsTab)) return raw as AiSettingsTab;
  if (raw && raw in LEGACY_TAB_ALIASES) return LEGACY_TAB_ALIASES[raw];
  return "usage";
}
