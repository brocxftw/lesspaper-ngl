import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ArtificialIntelligencePage } from "@/features/settings/ArtificialIntelligencePage";
import type { AIUsageSummary } from "@/lib/api/types";

const { idleMutation, policy, usageSummary, health, assignments } = vi.hoisted(() => ({
  idleMutation: {
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
  },
  policy: {
    privacy_mode: "private_hybrid",
    profile: "balanced",
    chat_provider_id: null,
    embedding_provider_id: null,
    vision_provider_id: null,
    allow_remote_embeddings: false,
    allow_remote_qa: true,
    allow_remote_vision: false,
    warn_before_remote: true,
    block_remote_ai: false,
    auto_enrichment: true,
    auto_tagging: true,
    retrieved_chunks: 8,
    max_context_tokens: 16000,
    max_output_tokens: 3072,
    conversation_history_tokens: 4000,
    parallel_llm_calls: 2,
    semantic_min_score: null,
    active_embedding_provider: null,
    active_embedding_model: null,
    active_embedding_dimension: null,
    enforcement_note: "lesspaper-ngl enforces these controls in application code.",
  },
  usageSummary: {
    range: "month",
    interval: "day",
    timezone: "UTC",
    starts_at: "2026-08-01T00:00:00Z",
    ends_at: "2026-08-18T00:00:00Z",
    totals: {
      requests: 0,
      input_tokens: null,
      output_tokens: null,
      duration_ms: null,
      estimated_cost: null,
      cost_currency: null,
      cost_coverage: "local_only",
    },
    time_series: [],
    by_provider: [],
    by_workload: [],
  } as AIUsageSummary,
  health: {
    ocr: { status: "available", provider: null, model: null, latency_ms: null, last_checked: null, error: null },
    indexing: { status: "available", provider: "Local", model: "gemma", latency_ms: 5, last_checked: null, error: null },
    embedding: { status: "available", provider: "Local", model: "embed", latency_ms: 18, last_checked: null, error: null },
    chat: { status: "available", provider: "Local", model: "qwen", latency_ms: 57, last_checked: null, error: null },
    auto_tagging: true,
    auto_enrichment: true,
  },
  assignments: [
    {
      role: "indexing",
      provider_id: "p1",
      provider_name: "LM Studio",
      model: "gemma",
      is_local: true,
      enabled: true,
      status: "configured",
      embedding_dimension: null,
      legacy_fallback: false,
    },
    {
      role: "embedding",
      provider_id: "p1",
      provider_name: "LM Studio",
      model: "embed",
      is_local: true,
      enabled: true,
      status: "configured",
      embedding_dimension: 1024,
      legacy_fallback: false,
    },
    {
      role: "chat",
      provider_id: "p1",
      provider_name: "LM Studio",
      model: "qwen",
      is_local: true,
      enabled: true,
      status: "configured",
      embedding_dimension: null,
      legacy_fallback: false,
    },
  ],
}));

vi.mock("@/lib/api/hooks", () => ({
  useAIUsage: () => ({ data: usageSummary, isLoading: false, error: null }),
  useAIAssignments: () => ({ data: assignments, isLoading: false, error: null }),
  useAIProviders: () => ({ data: [], isLoading: false }),
  useAIHealth: () => ({ data: health, isLoading: false }),
  useProviderModels: () => ({ data: { models: [], discoverable: true, message: null }, isFetching: false }),
  useUpdateAIAssignment: () => idleMutation,
  useCreateAIProvider: () => idleMutation,
  useUpdateAIProvider: () => idleMutation,
  useDeleteAIProvider: () => idleMutation,
  useTestAIProvider: () => idleMutation,
  useAIPolicy: () => ({ data: policy, isLoading: false }),
  useUpdateAIPolicy: () => idleMutation,
}));

function renderPage(search = "") {
  return render(
    <MemoryRouter initialEntries={[`/settings/artificial-intelligence${search}`]}>
      <ArtificialIntelligencePage />
    </MemoryRouter>,
  );
}

describe("Artificial Intelligence settings tabs", () => {
  it("shows Usage, Models, and Controls as the only tabs", () => {
    renderPage();
    expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
      "Usage",
      "Models",
      "Controls",
    ]);
  });

  it("shows the status banner on Usage", () => {
    renderPage();
    expect(screen.getByRole("status")).toHaveTextContent("AI available");
    expect(screen.getByRole("status")).toHaveTextContent("3 workloads configured");
    expect(screen.getByRole("status")).toHaveTextContent("Local-first");
  });

  it("shows usage empty and cost unavailable states", () => {
    renderPage();
    expect(screen.getByText(/No AI requests yet/i)).toBeInTheDocument();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText("Local models")).toBeInTheDocument();
  });

  it("renders a point when usage has only one time bucket", () => {
    usageSummary.totals.requests = 1;
    usageSummary.time_series = [
      {
        bucket: "2026-08-18T12:00:00Z",
        requests: 1,
        input_tokens: 10,
        output_tokens: 5,
        duration_ms: 100,
      },
    ];
    renderPage();
    const point = screen.getByTestId("usage-chart-point");
    expect(point).toBeInTheDocument();
    expect(screen.getByTestId("usage-chart-y-axis-label")).toHaveTextContent("Requests");
    expect(screen.getByTestId("usage-chart-x-axis-label")).toHaveTextContent("Time (UTC)");
    expect(screen.getAllByTestId("usage-chart-y-tick")).toHaveLength(2);
    expect(screen.getByTestId("usage-chart-x-tick")).toHaveTextContent("18 Aug");
    fireEvent.mouseEnter(point);
    expect(screen.getByTestId("usage-chart-tooltip")).toHaveTextContent("18 Aug 2026, 12:00 UTC");
    expect(screen.getByTestId("usage-chart-tooltip")).toHaveTextContent("Requests: 1");
    expect(screen.getAllByText("Average")).toHaveLength(3);
    expect(screen.getByText("Completed")).toBeInTheDocument();
    usageSummary.totals.requests = 0;
    usageSummary.time_series = [];
  });

  it("places workloads and providers in separate Models sections", () => {
    renderPage("?tab=models");
    expect(screen.getByRole("tab", { name: "Models" })).toHaveAttribute("data-state", "active");
    expect(screen.getByRole("heading", { name: "Providers" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "AI workloads" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Providers" }).compareDocumentPosition(
        screen.getByRole("heading", { name: "AI workloads" }),
      ) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(screen.getByText("Filing suggestions")).toBeInTheDocument();
    expect(screen.getByText("Ask AI")).toBeInTheDocument();
    expect(document.getElementById("providers")).toBeTruthy();
  });

  it("places privacy, automation, and response profile on Controls", () => {
    renderPage("?tab=controls");
    expect(screen.getByRole("tab", { name: "Controls" })).toHaveAttribute("data-state", "active");
    expect(screen.getByRole("heading", { name: "Privacy" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Automation" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Response profile" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeInTheDocument();
    expect(document.getElementById("ai-policy")).toBeTruthy();
    expect(screen.queryByText("Block all remote AI")).not.toBeInTheDocument();
    expect(screen.queryByText("Advanced: experimental vision")).not.toBeInTheDocument();
  });

  it("locks remote AI toggles in local-only mode", async () => {
    policy.privacy_mode = "local_only";
    renderPage("?tab=controls");
    const switches = screen.getAllByRole("switch");
    const remoteSwitches = switches.filter((node) =>
      ["Ask AI", "Embeddings", "Vision"].includes(node.getAttribute("aria-label") ?? ""),
    );
    for (const toggle of remoteSwitches) {
      expect(toggle).toBeDisabled();
    }
    policy.privacy_mode = "private_hybrid";
  });

  it("maps legacy providers tab onto Models", () => {
    renderPage("?tab=providers");
    expect(screen.getByRole("tab", { name: "Models" })).toHaveAttribute("data-state", "active");
    expect(screen.getByRole("heading", { name: "Providers" })).toBeInTheDocument();
  });

  it("maps legacy advanced tab onto Controls", () => {
    renderPage("?tab=advanced");
    expect(screen.getByRole("tab", { name: "Controls" })).toHaveAttribute("data-state", "active");
    expect(screen.getByRole("heading", { name: "Privacy" })).toBeInTheDocument();
  });

  it("maps legacy policy tab onto Controls", () => {
    renderPage("?tab=policy");
    expect(screen.getByRole("tab", { name: "Controls" })).toHaveAttribute("data-state", "active");
    expect(screen.getByRole("heading", { name: "Privacy" })).toBeInTheDocument();
  });

  it("does not ask for chat or embedding models on the provider form", () => {
    renderPage("?tab=models");
    fireEvent.click(screen.getByRole("button", { name: /Add provider/i }));
    expect(screen.getByRole("heading", { name: "Add provider" })).toBeInTheDocument();
    expect(screen.queryByText("Chat model")).not.toBeInTheDocument();
    expect(screen.queryByText("Embedding model")).not.toBeInTheDocument();
    expect(screen.getByText("Local provider")).toBeInTheDocument();
  });

  it("saves controls without block_remote_ai exposed in UI", () => {
    renderPage("?tab=controls");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(idleMutation.mutateAsync).toHaveBeenCalledWith(
      expect.objectContaining({
        block_remote_ai: false,
        profile: "balanced",
      }),
    );
  });
});
