import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DocumentsHeader } from "@/features/documents/DocumentsHeader";

describe("DocumentsHeader", () => {
  it("renders library view tabs without search, Ask AI, or Upload", () => {
    render(<DocumentsHeader view="all" onViewChange={() => undefined} />);
    expect(screen.getByRole("tab", { name: "All" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Recently added" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Unprocessed" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Search library")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask AI" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Upload" })).not.toBeInTheDocument();
  });
});
