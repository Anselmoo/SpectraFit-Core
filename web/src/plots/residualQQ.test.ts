// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { residualQQPlot } from "./residualQQ";
import type { QQBackend } from "../series/residualQQ";

const series: QQBackend[] = [
  {
    backend: "a",
    points: [
      { theoretical: -1.5, sample: -1.4 },
      { theoretical: -0.5, sample: -0.4 },
      { theoretical: 0.5, sample: 0.6 },
      { theoretical: 1.5, sample: 1.5 },
    ],
  },
  {
    backend: "b",
    points: [
      { theoretical: -1.0, sample: -0.8 },
      { theoretical: 0.0, sample: 0.1 },
      { theoretical: 1.0, sample: 1.2 },
    ],
  },
];

describe("residualQQPlot", () => {
  it("renders an SVGElement", () => {
    expect(residualQQPlot(series, { colors: { a: "#0cf", b: "#f80" } })).toBeInstanceOf(SVGElement);
  });

  it("empty series renders safely without throwing", () => {
    expect(residualQQPlot([], { colors: {} })).toBeInstanceOf(SVGElement);
  });

  it("honors an explicit width", () => {
    const svg = residualQQPlot(series, { colors: { a: "#0cf", b: "#f80" }, width: 640 });
    expect(svg.getAttribute("width")).toBe("640");
  });

  it("x axis label contains 'theoretical'", () => {
    const svg = residualQQPlot(series, { colors: { a: "#0cf" } });
    expect(svg.textContent).toMatch(/theoretical/i);
  });

  it("y axis label contains 'sample'", () => {
    const svg = residualQQPlot(series, { colors: { a: "#0cf" } });
    expect(svg.textContent).toMatch(/sample/i);
  });
});
