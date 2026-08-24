import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { AIChatPanel } from "./AIChatPanel";
import type { AskResponse } from "@/lib/api/types";

const { askMutation } = vi.hoisted(() => ({
  askMutation: {
    mutateAsync: vi.fn(),
    isPending: false,
  },
}));

vi.mock("@/lib/api/hooks", () => ({
  useAsk: () => askMutation,
  useAICapabilities: () => ({
    data: {
      privacy_mode: "private_hybrid",
      warn_before_remote_chat: false,
    },
  }),
  useAIHealth: () => ({
    data: {
      chat: {
        status: "available",
        provider: "local",
        model: "qwen",
        latency_ms: 1,
        last_checked: null,
        error: null,
      },
    },
  }),
  useFolders: () => ({ data: [] }),
}));

describe("AIChatPanel", () => {
  beforeEach(() => {
    askMutation.mutateAsync.mockReset();
    askMutation.isPending = false;
  });

  it("shows a generating indicator while the ask request is pending", () => {
    askMutation.isPending = true;
    render(
      <AIChatPanel
        compactComposer
        showScopeSelector={false}
        onCitationClick={vi.fn()}
      />,
    );
    expect(screen.getByText("Generating answer…")).toBeInTheDocument();
    expect(screen.getByText("lesspaper-ngl")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Generating answer" })).toBeDisabled();
  });

  it("renders markdown formatting in the answer body", async () => {
    const response: AskResponse = {
      answer: "Focus on **Influencing** and other risks.",
      citations: [],
      passages: [],
      provider: "local",
      model: "qwen",
      privacy_mode: "private_hybrid",
      is_local: true,
      insufficient_evidence: false,
    };
    askMutation.mutateAsync.mockResolvedValue(response);

    render(
      <AIChatPanel
        compactComposer
        showScopeSelector={false}
        onCitationClick={vi.fn()}
      />,
    );

    const input = screen.getByPlaceholderText("What would you like to know?");
    fireEvent.change(input, { target: { value: "What are the risks?" } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => {
      expect(screen.getByText("Influencing")).toBeInTheDocument();
    });
    expect(screen.queryByText(/\*\*Influencing\*\*/)).not.toBeInTheDocument();
    expect(screen.getByText("Influencing").tagName).toBe("STRONG");
  });
});
