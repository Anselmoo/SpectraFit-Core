// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { stabilityPlot } from "./stability";

const bands = [
  {
    backend: "lmfit",
    rows: [{ n: 5, mean: 0.99, lo: 0.98, hi: 1.0, backend: "lmfit" }],
  },
];

describe("stabilityPlot", () => {
  it("renders SVG", () => {
    expect(
      stabilityPlot(bands as any, { colors: { lmfit: "#0cf" } })
    ).toBeInstanceOf(SVGElement);
  });

  it("empty-safe", () => {
    expect(stabilityPlot([], { colors: {} })).toBeInstanceOf(SVGElement);
  });

  it("honors an explicit width", () => {
    const svg = stabilityPlot(bands as any, { colors: { lmfit: "#0cf" }, width: 460 });
    expect(svg.getAttribute("width")).toBe("460");
  });

  it("labels the y-axis with the real metric name when given one", () => {
    const svg = stabilityPlot(bands as any, { colors: { lmfit: "#0cf" }, metric: "iters" });
    const text = svg.textContent ?? "";
    expect(text).toContain("iterations");
    expect(text).not.toContain("value");
  });

  it("uses the spec's default 'iterations' y-label when no metric is supplied", () => {
    const svg = stabilityPlot(bands as any, { colors: { lmfit: "#0cf" } });
    expect(svg.textContent ?? "").toContain("iterations");
  });
});
