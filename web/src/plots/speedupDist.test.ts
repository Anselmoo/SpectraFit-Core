// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { speedupDistPlot } from "./speedupDist";
import type { SpeedupBox } from "../series/speedupDist";

const rows: SpeedupBox[] = [
  { backend: "a", values: [5, 10, 15, 20], p5: 5.75, p25: 8.75, median: 12.5, p75: 16.25, p95: 19.25 },
  { backend: "b", values: [1, 2, 3], p5: 1.1, p25: 1.5, median: 2, p75: 2.5, p95: 2.9 },
];

describe("speedupDistPlot", () => {
  it("renders an SVGElement", () => {
    expect(speedupDistPlot(rows, { colors: { a: "#0cf", b: "#f80" } })).toBeInstanceOf(SVGElement);
  });

  it("empty rows renders safely without throwing", () => {
    expect(speedupDistPlot([], { colors: {} })).toBeInstanceOf(SVGElement);
  });

  it("honors an explicit width", () => {
    const svg = speedupDistPlot(rows, { colors: { a: "#0cf", b: "#f80" }, width: 800 });
    expect(svg.getAttribute("width")).toBe("800");
  });

  it("x axis label contains 'speedup'", () => {
    const svg = speedupDistPlot(rows, { colors: { a: "#0cf" } });
    expect(svg.textContent).toMatch(/speedup/i);
  });
});
