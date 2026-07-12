/**
 * Per-case reduced-χ² distribution box plot (one horizontal box per backend).
 *
 * Mirrors the timing box plot pattern (horizontal boxes, whiskers p5→p75,
 * median tick) but drops p95 (AccuracyDist only has p5/p25/median/p75).
 * χ² ≈ 1 means the model fits the noise correctly; > 1 overfits noise,
 * < 1 may indicate overfitting or underestimated uncertainties.
 */
import * as Plot from "@observablehq/plot";
import type { AccuracyBox } from "../series/accuracy";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";

const svg = (p: any): SVGSVGElement =>
  p.tagName === "svg" ? p : p.querySelector("svg");

export function accuracyBoxPlot(
  rows: AccuracyBox[],
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const ids = rows.map((r) => r.backend);
  return svg(
    Plot.plot({
      width: o.width,
      height: Math.max(100, ids.length * 32 + 40),
      marginLeft: 96,
      style: {
        background: "transparent",
        color: "var(--ink-dim)",
        fontSize: "11px",
      },
      color: {
        domain: ids,
        range: ids.map((i) => o.colors[i] ?? "var(--accent)"),
      },
      ...axes(PLOT_SPECS["accuracy-dist"]),
      marks: [
        // Whisker: p5 → p75 (no p95 available in AccuracyDist)
        Plot.link(rows, {
          y: "backend",
          y2: "backend",
          x1: "p5",
          x2: "p75",
          stroke: "backend",
          strokeOpacity: 0.5,
        }),
        // IQR box: p25 → p75
        Plot.barX(rows, {
          y: "backend",
          x1: "p25",
          x2: "p75",
          fill: "backend",
          fillOpacity: 0.4,
        }),
        // Median tick
        Plot.tickX(rows, {
          y: "backend",
          x: "median",
          stroke: "backend",
          strokeWidth: 2,
        }),
        // Reference line at χ²_red = 1 (perfect fit)
        Plot.ruleX([1], { stroke: "var(--ink-faint)", strokeDasharray: "3,3", strokeOpacity: 0.6 }),
      ],
    })
  );
}
