// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { winnerPlot } from "./winner";

const bars = [
  { backend: "b", fraction: 0.88 },
  { backend: "a", fraction: 0.1 },
];

describe("winnerPlot", () => {
  it("renders SVG", () => {
    expect(
      winnerPlot(bars as any, { colors: { a: "#0cf", b: "#f80" } })
    ).toBeInstanceOf(SVGElement);
  });

  it("empty-safe", () => {
    expect(winnerPlot([], { colors: {} })).toBeInstanceOf(SVGElement);
  });

  it("honors an explicit width", () => {
    const svg = winnerPlot(bars as any, { colors: { a: "#0cf", b: "#f80" }, width: 520 });
    expect(svg.getAttribute("width")).toBe("520");
  });
});
