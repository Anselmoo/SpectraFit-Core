import * as Plot from "@observablehq/plot";
import type { ProfileSeries } from "../series/performanceProfile";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";

const unwrapSvg = (p: any): SVGSVGElement => {
  if (p instanceof SVGSVGElement) return p;
  const found = p.querySelector?.("svg");
  if (found instanceof SVGSVGElement) return found;
  return p as unknown as SVGSVGElement;
};

/**
 * Dolan-Moré performance profile: one non-decreasing step line per backend.
 * x = performance ratio τ on a LOG axis from 1 upward; y = fraction of cases ρ(τ)
 * solved within τ× of the fastest. ρ(1) is the height where each curve starts
 * (how often that backend is fastest); the right plateau is its robustness.
 */
export function performanceProfilePlot(
  series: ProfileSeries[],
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const ids = series.map((s) => s.backend);
  // Flatten to {backend, tau, rho}; the line uses curve "step-after" so each
  // point holds its ρ until the next τ — the canonical profile staircase.
  const rows = series.flatMap((s) => s.points.map((p) => ({ backend: s.backend, tau: p.tau, rho: p.rho })));
  const maxTau = Math.max(1, ...rows.map((r) => r.tau));
  return unwrapSvg(
    Plot.plot({
      width: o.width,
      height: 340,
      marginLeft: 56,
      marginBottom: 44,
      style: { background: "transparent", color: "var(--ink-dim)", fontSize: "11px" },
      color: { domain: ids, range: ids.map((i) => o.colors[i] ?? "var(--accent)") },
      ...axes(PLOT_SPECS["perf-profile"]),
      x: {
        ...axes(PLOT_SPECS["perf-profile"]).x,
        domain: [1, maxTau > 1 ? maxTau : 10],
      },
      y: {
        ...axes(PLOT_SPECS["perf-profile"]).y,
        domain: [0, 1],
      },
      marks: [
        Plot.line(rows, {
          x: "tau",
          y: "rho",
          stroke: "backend",
          strokeWidth: 1.6,
          curve: "step-after",
        }),
        Plot.ruleY([0]),
      ],
    })
  );
}
