import * as Plot from "@observablehq/plot";
import type { ParetoSeries } from "../series/pareto";
import { axes, niceDomain, dataExtent } from "./grammar";
import { PLOT_SPECS } from "./spec";
import { toSvg } from "./toSvg";

/**
 * Speed-vs-accuracy scatter over every case × backend; the line is the
 * non-dominated Pareto frontier. Upper-left (fast + accurate) is ideal.
 */
export function paretoPlot(
  s: ParetoSeries,
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const dots = s.flatMap((b) => b.points);
  const ids = s.map((b) => b.backend);
  const xDomain = niceDomain(dataExtent(dots.map((d) => d.x)), "log");
  return toSvg(
    Plot.plot({
      width: o.width,
      height: 360,
      marginLeft: 56,
      marginBottom: 44,
      style: { background: "transparent", color: "var(--ink-dim)", fontSize: "11px" },
      color: { domain: ids, range: ids.map((i) => o.colors[i] ?? "var(--accent)") },
      ...axes(PLOT_SPECS["pareto"]),
      x: { ...axes(PLOT_SPECS["pareto"]).x, domain: xDomain },
      marks: [
        Plot.dot(dots, { x: "x", y: "y", stroke: "backend", fill: "backend", fillOpacity: 0.35, r: 3 }),
        Plot.line(s.envelope, { x: "x", y: "y", stroke: "var(--ink)", strokeWidth: 1.5, strokeOpacity: 0.7 }),
        Plot.dot(s.envelope, { x: "x", y: "y", stroke: "var(--ink)", fill: "var(--ink)", r: 3.5 }),
      ],
    })
  );
}
