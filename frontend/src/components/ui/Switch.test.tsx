import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Switch } from "./Switch";

describe("Switch", () => {
  it("uses yellow and white for both switch states", () => {
    const { rerender } = render(<Switch aria-label="Remote AI" checked={false} />);
    expect(screen.getByRole("switch")).toHaveClass("bg-white");
    expect(screen.getByRole("switch").firstElementChild).toHaveClass("bg-accent");

    rerender(<Switch aria-label="Remote AI" checked />);
    expect(screen.getByRole("switch")).toHaveClass("bg-accent");
    expect(screen.getByRole("switch").firstElementChild).toHaveClass("bg-white");
  });
});
