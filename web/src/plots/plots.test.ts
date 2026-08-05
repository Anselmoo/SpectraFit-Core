import { describe, it, expect } from "vitest";
import { ciIntervalPlot } from "./index";
import { PLOT_SPECS } from "./spec";

const rows = [
  { caseId: "EZ-001", lo: 8, point: 10, hi: 12 },
  { caseId: "CX-001", lo: 15, point: 17, hi: 19 },
];

describe("ciIntervalPlot", () => {
  it("renders an SVG element from rows (jsdom)", () => {
    const el = ciIntervalPlot(rows, { spec: PLOT_SPECS["delta-r2-ci"] });
    expect(el).toBeInstanceOf(SVGElement);
    expect(el.querySelectorAll("*").length).toBeGreaterThan(0);
  });
  it("is empty-safe", () => {
    const el = ciIntervalPlot([], { spec: PLOT_SPECS["delta-r2-ci"] });
    expect(el).toBeInstanceOf(SVGElement);
  });
  it("can render a log x-scale without throwing", () => {
    const el = ciIntervalPlot(rows, { spec: PLOT_SPECS["speedup-ci"] });
    expect(el).toBeInstanceOf(SVGElement);
  });
  it("honors an explicit width", () => {
    const el = ciIntervalPlot(rows, { spec: PLOT_SPECS["delta-r2-ci"], width: 480 });
    expect(el.getAttribute("width")).toBe("480");
  });
});
