import * as Plot from "@observablehq/plot";
import type { SpeedupBox } from "../series/speedupDist";
import { axes, niceDomain, dataExtent } from "./grammar";
import { PLOT_SPECS } from "./spec";

/** Normalise Plot.plot output to always return an SVGSVGElement. */
const unwrapSvg = (p: any): SVGSVGElement => {
  if (p instanceof SVGSVGElement) return p;
  const found = p.querySelector?.("svg");
  if (found instanceof SVGSVGElement) return found;
  return p as unknown as SVGSVGElement;
};

/**
 * Box plot of speedup distribution per backend on a log x axis.
 * Mirrors timing.ts: link (p5→p95 whisker), barX (p25→p75 IQR), tickX (median).
 * A ruleX at x=1 marks the baseline (1× = baseline solver speed).
 */
export function speedupDistPlot(
  rows: SpeedupBox[],
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const ids = rows.map((r) => r.backend);
  // Include 1 in the domain so the baseline reference rule (ruleX at 1) is always visible
  const xDomain = niceDomain(dataExtent([1, ...rows.flatMap((r) => [r.p5, r.p95])]), "log");
  return unwrapSvg(
    Plot.plot({
      width: o.width,
      height: Math.max(120, ids.length * 32 + 40),
      marginLeft: 96,
      style: { background: "transparent", color: "var(--ink-dim)", fontSize: "11px" },
      color: {
        domain: ids,
        range: ids.map((i) => o.colors[i] ?? "var(--accent)"),
      },
      ...axes(PLOT_SPECS["speedup-dist"]),
      x: { ...axes(PLOT_SPECS["speedup-dist"]).x, domain: xDomain },
      marks: [
        // 1× baseline reference rule
        Plot.ruleX([1], { stroke: "var(--ink-faint)", strokeWidth: 1, strokeDasharray: "4 3" }),
        // Whisker: p5 → p95
        Plot.link(rows, {
          y: "backend",
          y2: "backend",
          x1: "p5",
          x2: "p95",
          stroke: "backend",
          strokeOpacity: 0.5,
        }),
        // IQR box: p25 → p75
        Plot.barX(rows, {
          y: "backend",
          x1: "p25",
          x2: "p75",
          fill: "backend",
          fillOpacity: 0.4,
        }),
        // Median tick
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
