import { describe, expect, it } from "vitest";
import { workloadDisplayLabel } from "@/features/settings/ai/workloadCopy";

describe("workloadDisplayLabel", () => {
  it("maps API workload keys to product labels", () => {
    expect(workloadDisplayLabel("indexing", "Indexing")).toBe("Filing suggestions");
    expect(workloadDisplayLabel("chat", "Chat")).toBe("Ask lesspaper-ngl");
    expect(workloadDisplayLabel("embeddings", "Embeddings")).toBe("Embeddings");
  });
});
