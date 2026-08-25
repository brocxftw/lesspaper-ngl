import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  AssignmentDialog,
  assignmentProviderChoices,
  rankDiscoveredModels,
} from "./AssignmentDialog";
import type { AIAssignment, AIDiscoveredModel } from "@/lib/api/types";

const assignment: AIAssignment = {
  role: "embedding",
  provider_id: "p1",
  provider_name: "OpenRouter",
  model: "",
  is_local: false,
  enabled: true,
  status: "configured",
  embedding_dimension: null,
  legacy_fallback: false,
};

vi.mock("@/lib/api/hooks", () => ({
  useAIProviders: () => ({
    data: [
      {
        id: "p1",
        name: "OpenRouter",
        enabled: true,
        supports_embeddings: true,
        supports_chat: true,
        supports_vision: false,
        is_local: false,
      },
    ],
  }),
  useProviderModels: () => ({
    data: {
      models: [
        { id: "openai/gpt-4o-mini", kind: "chat" },
        { id: "openai/text-embedding-3-small", kind: "embedding" },
        { id: "anthropic/claude-3.5-sonnet", kind: "chat" },
      ] satisfies AIDiscoveredModel[],
      discoverable: true,
      message: null,
    },
    isFetching: false,
  }),
  useUpdateAIAssignment: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
    error: null,
  }),
}));

describe("assignmentProviderChoices", () => {
  it("lists enabled providers even when they do not advertise embeddings", () => {
    const providers = [
      { id: "p1", enabled: true, supports_embeddings: false },
      { id: "p2", enabled: false, supports_embeddings: true },
    ];
    expect(assignmentProviderChoices(providers).map((item) => item.id)).toEqual(["p1"]);
  });
});

describe("rankDiscoveredModels", () => {
  const models: AIDiscoveredModel[] = [
    { id: "z-chat", kind: "chat" },
    { id: "a-embed", kind: "embedding" },
    { id: "m-other", kind: "other" },
  ];

  it("ranks embedding models first for the embedding workload", () => {
    expect(rankDiscoveredModels(models, "embedding").map((item) => item.id)).toEqual([
      "a-embed",
      "m-other",
      "z-chat",
    ]);
  });

  it("ranks chat models first for chat and indexing workloads", () => {
    expect(rankDiscoveredModels(models, "chat").map((item) => item.id)).toEqual([
      "z-chat",
      "m-other",
      "a-embed",
    ]);
  });
});

describe("AssignmentDialog discovered models", () => {
  it("uses discovered-only models with embedding recommendation copy", () => {
    render(<AssignmentDialog assignment={assignment} onClose={vi.fn()} />);
    expect(screen.queryByLabelText("Model ID")).not.toBeInTheDocument();
    expect(
      screen.getByText(
        "Prefer models marked Embedding. Chat models usually cannot produce vectors.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Select a discovered model")).toBeInTheDocument();
  });

  it("filters a large discovered-model list by ID", () => {
    render(<AssignmentDialog assignment={assignment} onClose={vi.fn()} />);

    fireEvent.change(screen.getByLabelText("Filter discovered models"), {
      target: { value: "claude" },
    });

    expect(screen.getByText("1 model shown")).toBeInTheDocument();
    expect(screen.getByText("anthropic/claude-3.5-sonnet")).toBeInTheDocument();
    expect(screen.queryByText("openai/gpt-4o-mini")).not.toBeInTheDocument();
  });
});
