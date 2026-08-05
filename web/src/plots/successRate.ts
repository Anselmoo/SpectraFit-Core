import * as Plot from "@observablehq/plot";
import type { SuccessRow } from "../series/successRate";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";
import { toSvg } from "./toSvg";

/**
 * Grouped bars: fraction of cases each backend solved successfully, faceted by
 * category. y axis is a percentage (0–100% converged).
 */
export function successRatePlot(
  rows: SuccessRow[],
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const ids = [...new Set(rows.map((r) => r.backend))];
  return toSvg(
    Plot.plot({
      width: o.width,
      height: 320,
      marginLeft: 52,
      marginBottom: 56,
      style: { background: "transparent", color: "var(--text-secondary)", fontSize: "11px" },
      color: { domain: ids, range: ids.map((i) => o.colors[i] ?? "var(--system-blue)") },
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
