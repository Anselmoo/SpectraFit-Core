// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { paretoPlot } from "./pareto";

const series = Object.assign(
  [
    { backend: "a", points: [{ x: 10, y: 0.99, caseId: "C1", backend: "a" }, { x: 2, y: 0.999, caseId: "C2", backend: "a" }] },
    { backend: "b", points: [{ x: 5, y: 0.90, caseId: "C1", backend: "b" }] },
  ],
  { envelope: [{ x: 2, y: 0.999, caseId: "C2", backend: "a" }, { x: 5, y: 0.90, caseId: "C1", backend: "b" }] },
);

describe("paretoPlot", () => {
  it("renders SVG", () => {
    expect(paretoPlot(series as any, { colors: { a: "#0cf", b: "#f80" } })).toBeInstanceOf(SVGElement);
  });
  it("empty-safe", () => {
    expect(paretoPlot(Object.assign([], { envelope: [] }) as any, { colors: {} })).toBeInstanceOf(SVGElement);
  });
  it("honors an explicit width", () => {
    const svg = paretoPlot(series as any, { colors: { a: "#0cf", b: "#f80" }, width: 620 });
    expect(svg.getAttribute("width")).toBe("620");
  });
});
