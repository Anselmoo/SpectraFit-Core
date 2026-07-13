// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { performanceProfilePlot } from "./performanceProfile";

const series = [
  { backend: "a", points: [{ tau: 1, rho: 0.33 }, { tau: 2, rho: 0.66 }, { tau: 5, rho: 1 }] },
  { backend: "b", points: [{ tau: 1, rho: 0.66 }, { tau: 4, rho: 1 }] },
];

describe("performanceProfilePlot", () => {
  it("renders SVG", () => {
    expect(performanceProfilePlot(series as any, { colors: { a: "#0cf", b: "#f80" } })).toBeInstanceOf(SVGElement);
  });
  it("empty-safe", () => {
    expect(performanceProfilePlot([], { colors: {} })).toBeInstanceOf(SVGElement);
  });
  it("honors an explicit width", () => {
    const svg = performanceProfilePlot(series as any, { colors: { a: "#0cf", b: "#f80" }, width: 620 });
    expect(svg.getAttribute("width")).toBe("620");
  });
});
