import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Katex } from "../Katex";

describe("Katex", () => {
  it("renders a LaTeX string into a .katex node", () => {
    const { container } = render(<Katex tex={"A \\cdot x^2"} />);
    expect(container.querySelector(".katex")).not.toBeNull();
  });

  it("does not throw on malformed TeX and shows the source", () => {
    const { container } = render(<Katex tex={"\\frac{"} />);
    expect(container.textContent).toContain("\\frac{");
  });
});
