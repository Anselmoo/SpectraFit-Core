import * as Plot from "@observablehq/plot";
import type { RecoveryBox } from "../series/recoveryError";
import { axes, niceDomain, dataExtent } from "./grammar";
import { PLOT_SPECS } from "./spec";

const unwrapSvg = (p: any): SVGSVGElement => {
  if (p instanceof SVGSVGElement) return p;
  const found = p.querySelector?.("svg");
  if (found instanceof SVGSVGElement) return found;
  return p as unknown as SVGSVGElement;
};

/**
 * Choose the x-axis scale for the suite recovery-error plot from the data.
 *
 * Recovery error is non-negative and spans orders of magnitude (a near-perfect
 * backend at ~0% next to a divergent one at ~300%). On a LINEAR axis the large
 * outlier squashes every accurate backend into the origin (EF-PLOTS-07 sibling).
 *  - strictly positive  → "log"    (cleanest spread)
 *  - non-negative w/ 0s  → "symlog" (log-like spread but defined at 0, where log
 *                                    cannot go — so a perfect 0% recovery is kept)
 *  - any negative value  → "linear" (defensive; |error| should never be negative)
 */
export function chooseRecoveryErrorScale(values: number[]): "log" | "symlog" | "linear" {
  const finite = values.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return "linear";
  if (finite.some((v) => v < 0)) return "linear";
  return finite.every((v) => v > 0) ? "log" : "symlog";
}

/**
 * Horizontal box per backend over the suite-wide parameter-recovery error:
 * p5–p95 whisker, p25–p75 box, median tick. Log x when every recovery error is
 * strictly positive (values span orders of magnitude); linear otherwise so a
 * zero error never breaks the axis. Lower and tighter is more accurate.
 *
 * The x-axis scale (log vs linear) is decided at runtime from the data. The
 * label is derived from the SAME runtime decision so they cannot silently
 * disagree — a log axis always carries "(log)" in its label (Invariant P /
 * EF-PLOTS-04).
 */
export function recoveryErrorPlot(
  rows: RecoveryBox[],
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const ids = rows.map((r) => r.backend);
  const scale = chooseRecoveryErrorScale(rows.flatMap((r) => r.values));

  // Single source of truth: the runtime scale drives both `type` and `label`, so
  // they cannot disagree. The label mirrors grammar.axisLabel's "(unit, marker)"
  // form, marking a non-linear axis ("log"/"symlog") just as a log axis is marked.
  const specX = PLOT_SPECS["recovery-error-suite"].x;
  const annot: string[] = [];
  if (specX.unit && specX.unit !== "—") annot.push(specX.unit);
  if (scale !== "linear") annot.push(scale);

  // Apply niceDomain for log and linear scales; symlog manages its own domain.
  const whiskers = rows.flatMap((r) => [r.p5, r.p95]);
  const domainOverride =
    scale === "log"
      ? niceDomain(dataExtent(whiskers), "log")
      : scale === "linear"
        ? niceDomain(dataExtent(whiskers), "linear")
        : undefined;

  const runtimeXAxis = {
    label: `${annot.length ? `${specX.label} (${annot.join(", ")})` : specX.label} →`,
    type: scale === "linear" ? undefined : scale,
    grid: true,
    ...(domainOverride ? { domain: domainOverride } : {}),
  };

  return unwrapSvg(
    Plot.plot({
      width: o.width,
      height: Math.max(120, ids.length * 32 + 48),
      marginLeft: 96,
      style: { background: "transparent", color: "var(--ink-dim)", fontSize: "11px" },
      color: { domain: ids, range: ids.map((i) => o.colors[i] ?? "var(--accent)") },
      ...axes(PLOT_SPECS["recovery-error-suite"]),
      x: runtimeXAxis,
      y: axes(PLOT_SPECS["recovery-error-suite"]).y,
      marks: [
        Plot.link(rows, {
          y: "backend",
          y2: "backend",
          x1: "p5",
          x2: "p95",
          stroke: "backend",
          strokeOpacity: 0.5,
        }),
        Plot.barX(rows, { y: "backend", x1: "p25", x2: "p75", fill: "backend", fillOpacity: 0.4 }),
        Plot.tickX(rows, { y: "backend", x: "median", stroke: "backend", strokeWidth: 2 }),
      ],
    })
  );
}
