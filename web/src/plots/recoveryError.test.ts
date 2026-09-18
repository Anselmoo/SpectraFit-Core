// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { recoveryErrorPlot, chooseRecoveryErrorScale } from "./recoveryError";

const rows = [
  { backend: "sf", values: [1, 2, 3], p5: 1, p25: 1.5, median: 2, p75: 2.5, p95: 3 },
  { backend: "lm", values: [10, 20, 30], p5: 10, p25: 15, median: 20, p75: 25, p95: 30 },
];

/** Extract the rendered x-axis label text from the SVG. */
function xAxisLabel(svg: SVGSVGElement): string {
  // Observable Plot renders axis labels as <text> elements; the x-axis label
  // is the one with aria-label="x-axis" or the last text in the x-axis group.
  // Simplest portable approach: collect all text content and find the one
  // that contains the word "recovery".
  const texts = Array.from(svg.querySelectorAll("text")).map((t) => t.textContent ?? "");
  return texts.find((t) => t.includes("recovery")) ?? "";
}

describe("recoveryErrorPlot", () => {
  it("renders SVG", () => {
    expect(recoveryErrorPlot(rows as any, { colors: { sf: "#0cf", lm: "#f80" } })).toBeInstanceOf(SVGElement);
  });
  it("empty-safe", () => {
    expect(recoveryErrorPlot([], { colors: {} })).toBeInstanceOf(SVGElement);
  });
  it("survives a zero value (no log-of-zero crash)", () => {
    const withZero = [{ backend: "sf", values: [0, 1], p5: 0, p25: 0.25, median: 0.5, p75: 0.75, p95: 1 }];
    expect(recoveryErrorPlot(withZero as any, { colors: { sf: "#0cf" } })).toBeInstanceOf(SVGElement);
  });
  it("honors an explicit width", () => {
    const svg = recoveryErrorPlot(rows as any, { colors: { sf: "#0cf", lm: "#f80" }, width: 560 });
    expect(svg.getAttribute("width")).toBe("560");
  });

  // EF-PLOTS-04: label must reflect the RUNTIME scale, not the static spec scale.
  // The grammar renders log annotations as "(unit, log)" when a unit is also present,
  // so we check for the presence of the word "log" in the label (not the exact
  // substring "(log)" which only appears on dimensionless log axes).
  it("log path: x-axis label marks log scale when all values are positive", () => {
    // rows has all-positive values → allPositive=true → log x-axis
    const svg = recoveryErrorPlot(rows as any, { colors: { sf: "#0cf", lm: "#f80" } });
    const label = xAxisLabel(svg);
    // Grammar produces "recovery error (%, log) →" — "log" is in the annotation.
    expect(label).toMatch(/\blog\b/);
  });
  // EF-PLOTS-07 sibling sweep: a zero error (perfect recovery) used to fall back
  // to a LINEAR axis, which squashes the accurate backends at the origin when one
  // backend (e.g. jax) is orders of magnitude worse. Recovery error is
  // non-negative, so symlog is the honest scale — log-like spread, defined at 0.
  it("symlog path: zero-containing data marks a symlog x-axis (spread, not squash)", () => {
    const withZero = [{ backend: "sf", values: [0, 1, 2], p5: 0, p25: 0.5, median: 1, p75: 1.5, p95: 2 }];
    const svg = recoveryErrorPlot(withZero as any, { colors: { sf: "#0cf" } });
    const label = xAxisLabel(svg);
    expect(label).toContain("symlog");
    expect(label).not.toMatch(/\blog\b/); // symlog, not a bare log axis
  });
});

describe("chooseRecoveryErrorScale (axis honesty — magnitude fairness)", () => {
  it("uses log when every recovery error is strictly positive", () => {
    expect(chooseRecoveryErrorScale([0.1, 2, 300])).toBe("log");
  });
  it("uses symlog when non-negative errors include a zero (perfect recovery)", () => {
    expect(chooseRecoveryErrorScale([0, 0.2, 300])).toBe("symlog");
  });
  it("falls back to linear only when a value is negative (should not happen for |error|)", () => {
    expect(chooseRecoveryErrorScale([-1, 2])).toBe("linear");
  });
  it("is linear for empty / all-non-finite input", () => {
    expect(chooseRecoveryErrorScale([])).toBe("linear");
    expect(chooseRecoveryErrorScale([NaN, Infinity])).toBe("linear");
  });
});
