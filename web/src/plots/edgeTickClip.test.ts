/**
 * R3: Edge tick labels on #case plots must not overflow the SVG right edge.
 *
 * Observable Plot renders tick labels centered on the tick position. When the
 * rightmost tick sits at the domain boundary, half the label extends beyond the
 * tick position into the right margin. With the default 20 px right margin, a
 * ~34 px label (e.g. "0.20") overflows by ~17 px — matching the observed clip.
 *
 * Fix: ensure marginRight ≥ 24 on the three affected #case plots:
 *   - residualQQPlot (x: theoretical quantiles, continuous linear axis)
 *   - recoveryPlot   (x: deviation from truth, continuous linear axis)
 *   - pullsPlot      (x: pull (est−truth)/σ, pinned domain [-4, 4])
 *
 * Measurement: Observable Plot encodes the right margin as the gap between the
 * SVG total width and the rightmost x-coordinate of the grid/tick lines.
 * For a 640px SVG with marginLeft=56 and marginRight=20, grid lines run to x2=620
 * (640 − 20 = 620). We read the maximum `x2` value across all grid/tick lines to
 * derive the right margin: rightMargin = svgWidth − max(x2).
 */
// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { residualQQPlot } from "./residualQQ";
import { recoveryPlot } from "./recovery";
import { pullsPlot } from "./pulls";
import type { QQBackend } from "../series/residualQQ";

// ---------------------------------------------------------------------------
// Helper: extract right margin from the SVG by reading grid/tick line x2 coords
// ---------------------------------------------------------------------------

function rightMarginFromSvg(svg: SVGSVGElement): number {
  const svgWidth = Number(svg.getAttribute("width") ?? "0");
  if (svgWidth === 0) return 0;

  // Observable Plot encodes the right edge of the plot area as the x2 of
  // the x-grid lines or the x-tick lines. The right margin = svgWidth − max(x2).
  const lines = Array.from(svg.querySelectorAll("line"));
  const x2values = lines
    .map((l) => Number(l.getAttribute("x2") ?? "0"))
    .filter((v) => v > 0 && v < svgWidth);

  if (x2values.length === 0) return 0;
  const maxX2 = Math.max(...x2values);
  return svgWidth - maxX2;
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const WIDTH = 640;

const qqSeries: QQBackend[] = [
  {
    backend: "spectrafit",
    points: [
      { theoretical: -2.0, sample: -1.9 },
      { theoretical: 0.0, sample: 0.1 },
      { theoretical: 2.0, sample: 2.1 },
    ],
  },
];

const recoveryRows = [
  { param: "amplitude", backend: "spectrafit", truth: 5, guess: 4, fit: 5.01 },
];

const pullEntries = [
  { backend: "spectrafit", pulls: [0.1, -0.3, 1.1], coverage: 0.9, absent: false },
];

// ---------------------------------------------------------------------------
// R3 assertions: marginRight ≥ 24 on the three affected #case plots
// ---------------------------------------------------------------------------

const MIN_RIGHT_MARGIN = 24;

describe("R3 edge-tick clip — #case plots must have marginRight ≥ 24", () => {
  it("residualQQPlot: right margin ≥ 24 px (edge ticks seat within SVG)", () => {
    const svg = residualQQPlot(qqSeries, { colors: { spectrafit: "#0cf" }, width: WIDTH });
    const rm = rightMarginFromSvg(svg);
    expect(rm).toBeGreaterThanOrEqual(MIN_RIGHT_MARGIN);
  });

  it("recoveryPlot: right margin ≥ 24 px (edge ticks seat within SVG)", () => {
    const svg = recoveryPlot(recoveryRows as any, { colors: { spectrafit: "#0cf" }, width: WIDTH });
    const rm = rightMarginFromSvg(svg);
    expect(rm).toBeGreaterThanOrEqual(MIN_RIGHT_MARGIN);
  });

  it("pullsPlot: right margin ≥ 24 px (edge ticks seat within SVG)", () => {
    const svg = pullsPlot(pullEntries as any, { colors: { spectrafit: "#0cf" }, width: WIDTH });
    const rm = rightMarginFromSvg(svg);
    expect(rm).toBeGreaterThanOrEqual(MIN_RIGHT_MARGIN);
  });
});
