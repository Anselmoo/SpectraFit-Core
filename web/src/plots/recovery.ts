import * as Plot from "@observablehq/plot";
import type { RecRow } from "../series/recovery";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";
import { toSvg } from "./toSvg";

export function recoveryPlot(
  rows: RecRow[],
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const ids = [...new Set(rows.map((r) => r.backend))];
  return toSvg(
    Plot.plot({
      width: o.width,
      height: Math.max(
        120,
        new Set(rows.map((r) => r.param)).size * 26 + 40
      ),
      marginLeft: 64,
      marginRight: 24,
      style: {
        background: "transparent",
        color: "var(--text-secondary)",
        fontSize: "11px",
      },
      color: {
        domain: ids,
        range: ids.map((i) => o.colors[i] ?? "var(--system-blue)"),
      },
      ...axes(PLOT_SPECS["recovery"]),
      marks: [
        // Truth reference: every parameter's truth maps to 0 on the normalized
        // axis (EF-PLOTS-07). Landing the fit dot on this line means recovered.
        Plot.ruleX([0], {
          stroke: "var(--text-secondary)",
          strokeOpacity: 0.5,
          strokeDasharray: "3,2",
        }),
        // guess → fit as a signed deviation relative to each parameter's own
        // scale, so disparate magnitudes no longer collapse onto one another.
        Plot.link(rows, {
          y: "param",
          x1: "guessDev",
          x2: "fitDev",
          stroke: "backend",
          markerEnd: "dot",
          strokeOpacity: 0.7,
        }),
      ],
    })
  );
}
