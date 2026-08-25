import { useMemo, useState } from "react";
import {
  useAIProviders,
  useProviderModels,
  useUpdateAIAssignment,
} from "@/lib/api/hooks";
import type {
  AIAssignment,
  AIDiscoveredModel,
  AIDiscoveredModelKind,
  AIWorkloadRole,
} from "@/lib/api/types";
import { Button } from "@/components/ui/Button";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/Dialog";
import { Input } from "@/components/ui/Input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import { WORKLOAD_COPY } from "./workloadCopy";

export function assignmentProviderChoices<T extends { enabled: boolean }>(
  providers: T[],
): T[] {
  return providers.filter((provider) => provider.enabled);
}

function kindRank(kind: AIDiscoveredModelKind, role: AIWorkloadRole): number {
  if (role === "embedding") {
    if (kind === "embedding") return 0;
    if (kind === "other") return 1;
    return 2;
  }
  if (kind === "chat") return 0;
  if (kind === "other") return 1;
  return 2;
}

export function rankDiscoveredModels(
  models: AIDiscoveredModel[],
  role: AIWorkloadRole,
): AIDiscoveredModel[] {
  return [...models].sort((a, b) => {
    const rankDiff = kindRank(a.kind, role) - kindRank(b.kind, role);
    if (rankDiff !== 0) return rankDiff;
    return a.id.localeCompare(b.id);
  });
}

function kindLabel(kind: AIDiscoveredModelKind): string {
  switch (kind) {
    case "embedding":
      return "Embedding";
    case "chat":
      return "Chat";
    default:
      return "Other";
  }
}

function roleRecommendation(role: AIWorkloadRole): string {
  if (role === "embedding") {
    return "Prefer models marked Embedding. Chat models usually cannot produce vectors.";
  }
  if (role === "chat") {
    return "Prefer models marked Chat. Embedding models are ranked lower for Ask AI.";
  }
  return "Prefer models marked Chat for filing suggestions. Embedding models are ranked lower.";
}

export function AssignmentDialog({
  assignment,
  onClose,
}: {
  assignment: AIAssignment;
  onClose: () => void;
}) {
  const { data: providers = [] } = useAIProviders();
  const mutation = useUpdateAIAssignment();
  const [providerId, setProviderId] = useState(assignment.provider_id || "");
  const [model, setModel] = useState(assignment.model || "");
  const [modelSearch, setModelSearch] = useState("");
  const { data: discovery, isFetching } = useProviderModels(providerId || null);
  const copy = WORKLOAD_COPY[assignment.role];
  const compatible = assignmentProviderChoices(providers);

  const rankedModels = useMemo(
    () => rankDiscoveredModels(discovery?.models ?? [], assignment.role),
    [discovery?.models, assignment.role],
  );
  const modelIds = useMemo(() => new Set(rankedModels.map((item) => item.id)), [rankedModels]);
  const selectedValid = Boolean(model && modelIds.has(model));
  const matchingModels = useMemo(() => {
    const query = modelSearch.trim().toLocaleLowerCase();
    const matches = query
      ? rankedModels.filter((item) => item.id.toLocaleLowerCase().includes(query))
      : rankedModels;
    const selected = rankedModels.find((item) => item.id === model);
    return selected && !matches.some((item) => item.id === selected.id)
      ? [selected, ...matches]
      : matches;
  }, [model, modelSearch, rankedModels]);

  const save = async () => {
    await mutation.mutateAsync({
      role: assignment.role,
      provider_id: providerId || null,
      model: providerId ? model.trim() || null : null,
    });
    onClose();
  };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Change model — {copy.title}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          <div>
            <label className="text-xs text-text-secondary">Provider</label>
            <Select
              value={providerId || "none"}
              onValueChange={(value) => {
                setProviderId(value === "none" ? "" : value);
                setModel("");
                setModelSearch("");
              }}
            >
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Unconfigured</SelectItem>
                {compatible.map((provider) => (
                  <SelectItem key={provider.id} value={provider.id}>
                    {provider.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {providerId && (
            <div className="space-y-3">
              <div>
                <label className="text-xs text-text-secondary">Model</label>
                {isFetching ? (
                  <p className="mt-2 text-xs text-text-muted">Discovering models…</p>
                ) : rankedModels.length ? (
                  <div className="mt-1 space-y-2">
                    <Input
                      aria-label="Filter discovered models"
                      value={modelSearch}
                      onChange={(event) => setModelSearch(event.target.value)}
                      placeholder="Filter models by ID"
                    />
                    <p className="text-xs text-text-muted" aria-live="polite">
                      {matchingModels.length} {matchingModels.length === 1 ? "model" : "models"} shown
                    </p>
                    <div
                      className="max-h-60 overflow-y-auto rounded-md border border-surface-border p-1"
                      role="listbox"
                      aria-label="Discovered models"
                    >
                      {matchingModels.length ? (
                        matchingModels.map((item) => (
                          <button
                            key={item.id}
                            type="button"
                            role="option"
                            aria-selected={model === item.id}
                            onClick={() => setModel(item.id)}
                            className="flex w-full items-center gap-2 rounded-sm px-2 py-1.5 text-left hover:bg-surface-hover focus:bg-surface-hover focus:outline-none"
                          >
                            <span className="font-mono text-xs text-text-primary">{item.id}</span>
                            <span className="rounded bg-surface-muted px-1.5 py-0.5 text-[10px] font-medium text-text-secondary">
                              {kindLabel(item.kind)}
                            </span>
                          </button>
                        ))
                      ) : (
                        <p className="px-2 py-3 text-xs text-text-muted">No models match this filter.</p>
                      )}
                    </div>
                    <p className="text-xs text-text-secondary">
                      {selectedValid ? `Selected: ${model}` : "Select a discovered model"}
                    </p>
                  </div>
                ) : (
                  <p className="mt-2 text-xs text-warning">
                    {discovery?.message ||
                      (assignment.role === "embedding"
                        ? "No embedding-capable models were found for this provider."
                        : "No models were returned by this provider.")}
                  </p>
                )}
                <p className="mt-1.5 text-xs text-text-muted">
                  {roleRecommendation(assignment.role)}
                </p>
              </div>
              {assignment.role === "embedding" && (
                <p className="text-xs text-warning">
                  Changing this assignment may require re-embedding existing documents.
                </p>
              )}
            </div>
          )}
          {mutation.error && (
            <p role="alert" className="text-sm text-danger">
              {mutation.error.message}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => void save()}
            disabled={
              mutation.isPending ||
              Boolean(providerId && (!model.trim() || !selectedValid))
            }
          >
            Save assignment
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
