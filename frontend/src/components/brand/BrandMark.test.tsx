import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrandLockup, BrandMark, BrandWordmark } from "@/components/brand/BrandMark";
import paperLogo from "@brand/paper_logo.svg";

describe("BrandMark", () => {
  it("uses the paper logo on dark surfaces", () => {
    const { container } = render(<BrandMark variant="on-dark" size={36} />);
    const img = container.querySelector("img");
    expect(img).toHaveAttribute("src", paperLogo);
  });

  it("uses the paper logo on light surfaces", () => {
    const { container } = render(<BrandMark variant="on-light" size={36} alt="lesspaper-ngl" />);
    const img = container.querySelector("img");
    expect(img).toHaveAttribute("src", paperLogo);
    expect(img).toHaveAttribute("alt", "lesspaper-ngl");
  });
});

describe("BrandWordmark", () => {
  it("renders lesspaper-ngl with a golden ngl suffix in Nunito Bold", () => {
    const { container } = render(<BrandWordmark variant="on-dark" />);
    expect(screen.getByText("lesspaper-ngl")).toBeInTheDocument();
    expect(container.querySelector(".text-navbar-accent")).toHaveTextContent("ngl");
    expect(container.firstChild).toHaveClass("font-brand", "font-bold");
  });
});

describe("BrandLockup", () => {
  it("pairs the mark with the wordmark", () => {
    const { container } = render(
      <BrandLockup variant="on-light" markSize={28} wordmarkClassName="text-2xl" />,
    );
    expect(container.querySelector("img")).toHaveAttribute("src", paperLogo);
    expect(screen.getByText("lesspaper-ngl")).toBeInTheDocument();
  });
});
