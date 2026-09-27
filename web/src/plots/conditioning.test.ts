// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { conditioningPlot } from "./conditioning";

const rows = [
  { backend: "a", kappa: 1e7, illPosed: true, absent: false },
  { backend: "c", kappa: null, illPosed: false, absent: true },
];

describe("conditioningPlot", () => {
  it("renders SVG and shows an explicit lane for absent κ(J) backends", () => {
    const svg = conditioningPlot(rows as any, { colors: { a: "#0cf" } });
    expect(svg).toBeInstanceOf(SVGElement);
    const text = svg.textContent ?? "";
    // Absent backend "c" keeps its lane (y-axis tick) and a "not exposed" label.
    expect(text).toContain("c");
    expect(text).toContain("not exposed");
  });
  it("renders an absent-only roster (no present κ(J)) without crashing", () => {
    const onlyAbsent = [{ backend: "sf", kappa: null, illPosed: false, absent: true }];
    const svg = conditioningPlot(onlyAbsent as any, { colors: {} });
    expect(svg).toBeInstanceOf(SVGElement);
    expect(svg.textContent ?? "").toContain("not exposed");
  });
  it("empty-safe", () => {
    expect(conditioningPlot([], { colors: {} })).toBeInstanceOf(SVGElement);
  });
  it("honors an explicit width", () => {
    const svg = conditioningPlot(rows as any, { colors: { a: "#0cf" }, width: 440 });
    expect(svg.getAttribute("width")).toBe("440");
  });
});
