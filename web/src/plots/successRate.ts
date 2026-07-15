import * as Plot from "@observablehq/plot";
import type { SuccessRow } from "../series/successRate";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";

const unwrapSvg = (p: any): SVGSVGElement => {
  if (p instanceof SVGSVGElement) return p;
  const found = p.querySelector?.("svg");
  if (found instanceof SVGSVGElement) return found;
  return p as unknown as SVGSVGElement;
};

/**
 * Grouped bars: fraction of cases each backend solved successfully, faceted by
 * category. y axis is a percentage (0–100% converged).
 */
export function successRatePlot(
  rows: SuccessRow[],
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const ids = [...new Set(rows.map((r) => r.backend))];
  return unwrapSvg(
    Plot.plot({
      width: o.width,
      height: 320,
      marginLeft: 52,
      marginBottom: 56,
      style: { background: "transparent", color: "var(--ink-dim)", fontSize: "11px" },
      color: { domain: ids, range: ids.map((i) => o.colors[i] ?? "var(--accent)") },
      ...axes(PLOT_SPECS["success-rate"]),
      fx: { label: "category", tickRotate: -20 },
      x: { axis: null, domain: ids },
      y: { ...axes(PLOT_SPECS["success-rate"]).y, percent: true, domain: [0, 1] },
      marks: [
        Plot.barY(rows, { fx: "category", x: "backend", y: "successFraction", fill: "backend" }),
        Plot.ruleY([0]),
      ],
    })
  );
}
