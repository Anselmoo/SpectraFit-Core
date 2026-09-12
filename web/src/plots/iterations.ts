import * as Plot from "@observablehq/plot";
import type { IterationEntry } from "../series/iterations";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";
import { toSvg } from "./toSvg";

/**
 * Horizontal bar chart of iteration counts per backend.
 * Linear x axis (not log — iteration counts are non-negative integers that
 * may legitimately be 0). Color by backend; y encodes the backend label.
 */
export function iterationsPlot(
  rows: IterationEntry[],
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const ids = rows.map((r) => r.backend);
  return toSvg(
    Plot.plot({
      width: o.width,
      height: Math.max(100, ids.length * 30 + 40),
      marginLeft: 96,
      style: { background: "transparent", color: "var(--text-secondary)", fontSize: "11px" },
      color: {
        domain: ids,
        range: ids.map((i) => o.colors[i] ?? "var(--system-blue)"),
      },
      ...axes(PLOT_SPECS["iterations"]),
      marks: [
        Plot.barX(rows, {
          y: "backend",
          x: "nIter",
          fill: "backend",
          fillOpacity: 0.7,
        }),
        Plot.tickX(rows, {
          y: "backend",
          x: "nIter",
          stroke: "backend",
          strokeWidth: 1.5,
        }),
      ],
    })
  );
}
