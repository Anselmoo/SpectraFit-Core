import * as Plot from "@observablehq/plot";
import type { StabBand, StabMetric } from "../series/stability";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";

const svg = (p: any): SVGSVGElement =>
  p.tagName === "svg" ? p : p.querySelector("svg");

/** Human-readable y-axis label for each reproducibility metric. */
const METRIC_LABEL: Record<StabMetric, string> = {
  r2: "r²",
  rmse: "RMSE",
  redChi2: "reduced χ²",
  iters: "iterations",
};

export function stabilityPlot(
  bands: StabBand[],
  o: { colors: Record<string, string>; width?: number; metric?: StabMetric }
): SVGSVGElement {
  const grammar = axes(PLOT_SPECS["reproducibility"]);
  // Default y-axis comes from the spec; an explicit metric overrides the label
  // (the spec's default is the `iters` metric).
  const y = o.metric ? { ...grammar.y, label: METRIC_LABEL[o.metric] } : grammar.y;
  const rows = bands.flatMap((b) => b.rows);
  const ids = bands.map((b) => b.backend);

  return svg(
    Plot.plot({
      width: o.width,
      height: 220,
      marginLeft: 56,
      style: {
        background: "transparent",
        color: "var(--ink-dim)",
        fontSize: "11px",
      },
      color: {
        domain: ids,
        range: ids.map((i) => o.colors[i] ?? "var(--accent)"),
      },
      x: grammar.x,
      y,
      marks: [
        Plot.areaY(rows, {
          x: "n",
          y1: "lo",
          y2: "hi",
          fill: "backend",
          fillOpacity: 0.18,
        }),
        Plot.line(rows, { x: "n", y: "mean", stroke: "backend" }),
      ],
    })
  );
}
