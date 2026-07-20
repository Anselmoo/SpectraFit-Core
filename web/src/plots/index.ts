/**
 * Plots module — @observablehq/plot chart factories.
 * Colors via CSS vars only; tick formatting via tickLabels (no .toFixed literals).
 */
import * as Plot from "@observablehq/plot";
import { tickLabels } from "../series";
import type { CIRow } from "../series";
import { axes } from "./grammar";
import type { PlotSpec } from "./spec";

export type { CIRow };

export interface CIPlotOpts {
  /** The plot's axis grammar source — drives x label/scale/grid (delta-r2-ci / speedup-ci). */
  spec: PlotSpec;
  height?: number;
  width?: number;
}

/**
 * Horizontal CI intervals: a dot at `point` with a rule from `lo`..`hi` per case.
 * Always returns an SVGSVGElement — unwraps Plot's figure wrapper when present.
 *
 * The x-axis derives entirely from the supplied `PlotSpec` via the shared grammar;
 * the y-axis stays the categorical "case" list. Shared by the delta-r2-ci and
 * speedup-ci panels, which pass their respective specs.
 */
export function ciIntervalPlot(rows: CIRow[], o: CIPlotOpts): SVGSVGElement {
  const ids = rows.map((r) => r.caseId);
  const isLog = o.spec.x.scale === "log";
  const grammar = axes(o.spec);
  const result = Plot.plot({
    width: o.width,
    height: o.height ?? Math.max(120, rows.length * 18 + 40),
    marginLeft: 84,
    marginRight: 16,
    style: {
      background: "transparent",
      color: "var(--ink-dim)",
      fontSize: "11px",
    },
    x: {
      ...grammar.x,
      tickFormat: (t: number) =>
        tickLabels([t], isLog ? "log" : "linear")[0],
    },
    y: { domain: ids, label: "case" },
    marks: [
      Plot.ruleY(rows, {
        y: "caseId",
        x1: "lo",
        x2: "hi",
        stroke: "var(--accent)",
        strokeOpacity: 0.45,
        strokeWidth: 2,
      }),
      Plot.dot(rows, {
        y: "caseId",
        x: "point",
        fill: "var(--accent)",
        r: 3,
      }),
    ],
  });

  // Plot.plot may return either a bare <svg> or an <figure> wrapper containing one.
  // Normalise to always return the SVGSVGElement.
  if (result instanceof SVGSVGElement) return result;
  const svg = result.querySelector?.("svg");
  if (svg instanceof SVGSVGElement) return svg;
  // Fallback: return whatever element we got cast as SVGSVGElement so the
  // test can at least introspect it (shouldn't happen in practice).
  return result as unknown as SVGSVGElement;
}

// Legacy stubs preserved for existing consumers
export type PlotOptions = Record<string, unknown>;
export function emptyPlotOptions(): PlotOptions {
  return {};
}
