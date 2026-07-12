// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { timingBoxPlot } from "./timing";

const rows = [
  { backend: "lmfit", p5: 1, p25: 2, median: 3, p75: 4, p95: 5 },
];

describe("timingBoxPlot", () => {
  it("renders SVG", () => {
    expect(
      timingBoxPlot(rows as any, { colors: { lmfit: "#0cf" } })
    ).toBeInstanceOf(SVGElement);
  });

  it("empty-safe", () => {
    expect(timingBoxPlot([], { colors: {} })).toBeInstanceOf(SVGElement);
  });

  it("honors an explicit width", () => {
    const svg = timingBoxPlot(rows as any, { colors: { lmfit: "#0cf" }, width: 540 });
    expect(svg.getAttribute("width")).toBe("540");
  });
});
