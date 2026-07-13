import * as Plot from "@observablehq/plot";
import type { GridCell } from "../series/saturation";
import { SATURATION_FAIL_THRESHOLD } from "../series/saturation";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";

/**
 * @param o.categoryCounts — optional map from category id → case count.
 *   When provided, each category label on the y-axis is annotated with "(N=…)".
 */
export function saturationHeatmap(
  rows: GridCell[],
  o: { width?: number; categoryCounts?: Record<string, number> }
): SVGSVGElement {
  const cats = [...new Set(rows.map((r) => r.category))];
  const counts = o.categoryCounts;

  const agreeRows = rows.filter((r) => !r.failed);
  const failRows = rows.filter((r) => r.failed);

  // Scale-cue note: embedded in the SVG as a text mark so it is always visible
  // (no external caption element required). Placed at the bottom-left corner of
  // the plot area. The note makes explicit that 0.9 is the floor of the agree
  // band — not zero — so a referee can distinguish a saturated cell from a
  // moderately-good one. Failed cells (r²<0.9) are rendered in var(--fail) to
  // make a catastrophic backend failure visually unmistakable.
  const NOTE_TEXT = `color floor r²=${SATURATION_FAIL_THRESHOLD}; failed fits (r²<${SATURATION_FAIL_THRESHOLD}) in red`;

  const plot = Plot.plot({
    width: o.width,
    height: Math.max(120, cats.length * 30 + 80),
    marginLeft: 116,
    marginBottom: 90,
    style: { background: "transparent", color: "var(--ink-dim)", fontSize: "11px" },
    ...axes(PLOT_SPECS["saturation"]),
    x: { ...axes(PLOT_SPECS["saturation"]).x, tickRotate: -30 },
    y: {
      ...axes(PLOT_SPECS["saturation"]).y,
      tickFormat: counts
        ? (cat: string) => `${cat} (N=${counts[cat] ?? "?"})`
        : (cat: string) => cat,
    },
    // tight scale so the optfn discrimination pops; saturated cells max out.
    // clamp:true is intentional for the agree-band; failed cells bypass this
    // scale entirely and receive a fixed --fail fill via a separate mark.
    color: { type: "linear", domain: [0.9, 1.0], clamp: true, scheme: "BuGn", legend: false },
    marks: [
      // Agree-band cells (r²≥0.9): green sequential scale, tight [0.9,1.0] domain.
      Plot.cell(agreeRows, { x: "backend", y: "category", fill: "r2", inset: 1 }),
      // Failed cells (r²<0.9): fixed --fail fill so a catastrophic backend
      // failure is visually unmistakable — never confused with the 0.9 floor.
      Plot.cell(failRows, {
        x: "backend",
        y: "category",
        fill: "var(--fail)",
        inset: 1,
      }),
      // Scale-cue note: always visible inside the SVG, no legend required.
      Plot.text([NOTE_TEXT], {
        frameAnchor: "bottom-left",
        fill: "var(--ink-faint)",
        fontSize: 9,
        fontStyle: "italic",
        dy: -4,
      }),
    ],
  });

  // Plot.plot may return either a bare <svg> or a <figure> wrapper containing one.
  // Normalise to always return the SVGSVGElement — same pattern as ciIntervalPlot.
  if (plot instanceof SVGSVGElement) return plot;
  const svg = plot.querySelector?.("svg");
  if (svg instanceof SVGSVGElement) return svg;
  return plot as unknown as SVGSVGElement;
}
