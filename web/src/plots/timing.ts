import * as Plot from "@observablehq/plot";
import type { TimingBox } from "../series/timing";
import { axes, niceDomain, dataExtent } from "./grammar";
import { PLOT_SPECS } from "./spec";

const svg = (p: any): SVGSVGElement =>
  p.tagName === "svg" ? p : p.querySelector("svg");

export function timingBoxPlot(
  rows: TimingBox[],
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const ids = rows.map((r) => r.backend);
  const xDomain = niceDomain(dataExtent(rows.flatMap((r) => [r.p5, r.p95])), "log");
  return svg(
    Plot.plot({
      width: o.width,
      height: Math.max(120, ids.length * 32 + 40),
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
      ...axes(PLOT_SPECS["timing"]),
      x: { ...axes(PLOT_SPECS["timing"]).x, domain: xDomain },
      marks: [
        Plot.link(rows, {
          y: "backend",
          y2: "backend",
          x1: "p5",
          x2: "p95",
          stroke: "backend",
          strokeOpacity: 0.5,
        }),
        Plot.barX(rows, {
          y: "backend",
          x1: "p25",
          x2: "p75",
          fill: "backend",
          fillOpacity: 0.4,
        }),
        Plot.tickX(rows, {
          y: "backend",
          x: "median",
          stroke: "backend",
          strokeWidth: 2,
        }),
      ],
    })
  );
}
