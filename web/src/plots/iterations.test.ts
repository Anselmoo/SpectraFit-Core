// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { iterationsPlot } from "./iterations";
import type { IterationEntry } from "../series/iterations";

const rows: IterationEntry[] = [
  { backend: "a", nIter: 12 },
  { backend: "b", nIter: 7 },
  { backend: "c", nIter: 25 },
];

describe("iterationsPlot", () => {
  it("renders an SVGElement", () => {
    expect(iterationsPlot(rows, { colors: { a: "#0cf", b: "#f80", c: "#8f0" } })).toBeInstanceOf(SVGElement);
  });

  it("empty rows renders safely without throwing", () => {
    expect(iterationsPlot([], { colors: {} })).toBeInstanceOf(SVGElement);
  });

  it("honors an explicit width", () => {
    const svg = iterationsPlot(rows, { colors: { a: "#0cf", b: "#f80", c: "#8f0" }, width: 500 });
    expect(svg.getAttribute("width")).toBe("500");
  });

  it("x axis label contains 'iterations'", () => {
    const svg = iterationsPlot(rows, { colors: { a: "#0cf" } });
    expect(svg.textContent).toMatch(/iterations/i);
  });
});
