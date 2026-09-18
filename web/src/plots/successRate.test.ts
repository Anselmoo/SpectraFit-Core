// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { successRatePlot } from "./successRate";

const rows = [
  { category: "easy", backend: "a", successFraction: 0.5 },
  { category: "easy", backend: "b", successFraction: 1 },
  { category: "hard", backend: "a", successFraction: 1 },
  { category: "hard", backend: "b", successFraction: 0 },
];

describe("successRatePlot", () => {
  it("renders SVG", () => {
    expect(successRatePlot(rows as any, { colors: { a: "#0cf", b: "#f80" } })).toBeInstanceOf(SVGElement);
  });
  it("empty-safe", () => {
    expect(successRatePlot([], { colors: {} })).toBeInstanceOf(SVGElement);
  });
  it("honors an explicit width", () => {
    const svg = successRatePlot(rows as any, { colors: { a: "#0cf", b: "#f80" }, width: 600 });
    expect(svg.getAttribute("width")).toBe("600");
  });
});
