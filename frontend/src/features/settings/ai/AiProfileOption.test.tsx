import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AiProfileOption } from "./AiProfileOption";

describe("AiProfileOption", () => {
  it("uses a yellow radio with a white center when selected", () => {
    render(
      <AiProfileOption
        label="Custom"
        tagline="Manual tuning"
        spec="User-defined limits"
        selected
        onSelect={vi.fn()}
      />,
    );

    const indicator = screen.getByRole("button", { name: /custom/i }).firstElementChild;
    expect(indicator).toHaveClass("bg-accent");
    expect(indicator?.firstElementChild).toHaveClass("bg-white");
  });
});
