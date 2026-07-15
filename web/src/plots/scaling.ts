import * as Plot from "@observablehq/plot";
import type { ScalingLine } from "../series/scaling";
import { axes, niceDomain, dataExtent } from "./grammar";
import { PLOT_SPECS } from "./spec";

const svg = (p: any): SVGSVGElement =>
  p.tagName === "svg" ? p : p.querySelector("svg");

export function scalingPlot(
  lines: ScalingLine[],
  o: { colors: Record<string, string>; crossN?: number; width?: number }
): SVGSVGElement {
  const rows = lines.flatMap((l) => l.rows);
  const ids = lines.map((l) => l.backend);
  const xDomain = niceDomain(dataExtent(rows.map((r) => r.n)), "log");
  const yDomain = niceDomain(dataExtent(rows.map((r) => r.ms)), "log");
  return svg(
    Plot.plot({
      width: o.width,
      height: 220,
      marginLeft: 52,
      style: {
        background: "transparent",
        color: "var(--ink-dim)",
        fontSize: "11px",
      },
      color: {
        domain: ids,
        range: ids.map((i) => o.colors[i] ?? "var(--accent)"),
      },
      ...axes(PLOT_SPECS["scaling"]),
      x: { ...axes(PLOT_SPECS["scaling"]).x, domain: xDomain },
      y: { ...axes(PLOT_SPECS["scaling"]).y, domain: yDomain },
      marks: [
        Plot.line(rows, { x: "n", y: "ms", stroke: "backend" }),
        ...(o.crossN
          ? [
              Plot.ruleX([o.crossN], {
                stroke: "var(--hairline)",
                strokeDasharray: "3,3",
              }),
            ]
          : []),
      ],
    })
  );
}
