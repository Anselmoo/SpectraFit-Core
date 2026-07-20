// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { scalingPlot } from "./scaling";

const lines = [
  {
    backend: "lmfit",
    rows: [
      { n: 128, ms: 1.2, backend: "lmfit" },
      { n: 512, ms: 5.1, backend: "lmfit" },
    ],
  },
];

describe("scalingPlot", () => {
  it("renders SVG with crossover", () => {
    expect(
      scalingPlot(lines as any, { colors: { lmfit: "#0cf" }, crossN: 1024 })
    ).toBeInstanceOf(SVGElement);
  });

  it("empty-safe", () => {
    expect(scalingPlot([], { colors: {} })).toBeInstanceOf(SVGElement);
  });

  it("honors an explicit width", () => {
    const svg = scalingPlot(lines as any, { colors: { lmfit: "#0cf" }, width: 700 });
    expect(svg.getAttribute("width")).toBe("700");
  });
});
