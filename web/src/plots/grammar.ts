/**
 * The ONE visual grammar (Invariant P, render side).
 *
 * Plots stop hand-coding axis labels/scales/grid. They derive them from their
 * `PlotSpec` through this single helper, so the grammar is consistent by
 * construction: every quantitative axis gets a direction affordance (`→`/`↑`),
 * a log axis is always marked `(log)`, units are always shown, and the value
 * axes are gridded uniformly. The per-plot marks stay bespoke; only the axis
 * grammar is centralized here.
 *
 * Academic axis law (Track 2, Dye voice — one law, all charts):
 *   • log scale, ≥2 decades → decade-aligned bounds (floor/ceil on log10).
 *   • log scale, <2 decades → 1-2-5-10 ladder (≤2× dead space guaranteed).
 *   • linear scale           → nice-step rounding hugging the data.
 *   • min ≤ 0 on log         → clamped to LOG_FLOOR (never 0 on a log axis).
 * Charts that need tight auto-scaling pass dataExtent([...values]) to niceDomain
 * and override their axis domain after the spread.
 */
import type { ScaleOptions } from "@observablehq/plot";

import type { AxisSpec, PlotSpec } from "./spec";

// ---------------------------------------------------------------------------
// Academic axis law helpers (Track 2)
// ---------------------------------------------------------------------------

/** Smallest positive value we'll allow as a log-axis lower bound. */
const LOG_FLOOR = 1e-9;

/**
 * "Nice" log-scale lower bound: the largest value in the 1-2-5-10 ladder
 * that is ≤ v. For [3, 7]: niceLogFloor(3) = 2 (within 2× of 3). ✓
 * Always returns a positive value.
 */
function niceLogFloor(v: number): number {
  if (v <= 0) return LOG_FLOOR;
  const exp = Math.floor(Math.log10(v));
  const mag = Math.pow(10, exp);
  const steps = [1, 2, 5];
  let best = mag * steps[0];
  for (const s of steps) {
    const candidate = mag * s;
    if (candidate <= v) best = candidate;
  }
  return best;
}

/**
 * "Nice" log-scale upper bound: the smallest value in the 1-2-5-10 ladder
 * that is ≥ v. For [3, 7]: niceLogCeil(7) = 10 (within 2× of 7). ✓
 * For [3, 30]: niceLogCeil(30) = 50 (within 2× of 30). ✓
 */
function niceLogCeil(v: number): number {
  if (v <= 0) return 10;
  const exp = Math.floor(Math.log10(v));
  const mag = Math.pow(10, exp);
  const candidates = [mag * 1, mag * 2, mag * 5, mag * 10];
  for (const c of candidates) {
    if (c >= v) return c;
  }
  return mag * 10;
}

/**
 * Compute a tight "nice" domain for a chart axis.
 *
 * @param dataRange - [min, max] of the actual data on this axis.
 * @param scale     - "log" or "linear"
 * @returns         A [lo, hi] domain pair appropriate for the axis type.
 *
 * For log scale:
 *   • Clamps min to LOG_FLOOR when data contains 0 or negative values.
 *   • ≥ 2 decades: decade-aligned (10^floor, 10^ceil).
 *   • < 2 decades: expand to the next nice 1-2-5-10 boundary in each
 *     direction, guaranteeing ≤ 2× dead space on either side.
 *
 * For linear scale:
 *   • Computes a step size (10^floor(log10(range/5))), then snaps lo down
 *     and hi up to the nearest multiple of that step.
 */
export function niceDomain(
  dataRange: [number, number],
  scale: "log" | "linear"
): [number, number] {
  let [dMin, dMax] = dataRange;

  if (scale === "log") {
    // Guard: log axis cannot have min ≤ 0
    if (dMin <= 0) dMin = dMax > 0 ? Math.max(dMax * 1e-4, LOG_FLOOR) : LOG_FLOOR;
    if (dMax <= 0) dMax = dMin * 1000; // all-negative input: fabricate a safe range

    // Actual decade span: use ratio of data values, not exponent arithmetic.
    // exponent arithmetic (ceil - floor) can over-count by 1 for values like [3, 30].
    const actualDecades = Math.log10(dMax / dMin);

    if (actualDecades >= 2) {
      // ≥ 2 decades: pure decade alignment (powers of 10)
      const loExp = Math.floor(Math.log10(dMin));
      const hiExp = Math.ceil(Math.log10(dMax));
      return [Math.pow(10, loExp), Math.pow(10, hiExp)];
    } else {
      // < 2 decades: use a "nice" sub-decade boundary within 2× of data on both sides.
      const lo = niceLogFloor(dMin);
      const hi = niceLogCeil(dMax);
      return [lo, hi];
    }
  } else {
    // linear scale: nice-step rounding
    const range = dMax - dMin;
    if (range === 0) {
      // Degenerate: single value
      const pad = Math.abs(dMin) * 0.1 || 1;
      return [dMin - pad, dMax + pad];
    }

    // Nice step: one power of 10 below range/5 (5 "nice" ticks target)
    const rawStep = range / 5;
    const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
    // Round step to 1, 2, or 5 × magnitude
    let step = mag;
    if (rawStep / mag >= 4.5) step = mag * 5;
    else if (rawStep / mag >= 1.5) step = mag * 2;

    const lo = Math.floor(dMin / step) * step;
    const hi = Math.ceil(dMax / step) * step;
    return [lo, hi];
  }
}

/**
 * Compute the [min, max] extent of a flat numeric array.
 * Returns [1, 10] as a safe default when the array is empty or all-NaN/Inf.
 */
export function dataExtent(values: number[]): [number, number] {
  const finite = values.filter((v) => isFinite(v));
  if (finite.length === 0) return [1, 10];
  const lo = Math.min(...finite);
  const hi = Math.max(...finite);
  // Degenerate single-value: add 50% padding
  if (lo === hi) return [lo * 0.5 || 0.1, hi * 2 || 10];
  return [lo, hi];
}

// ---------------------------------------------------------------------------
// Grammar helpers (Invariant P)
// ---------------------------------------------------------------------------

/**
 * Compose the canonical axis label from a spec axis:
 *   x → "quantity (unit, log) →"   ·   y → "↑ quantity (unit, log)"
 * The unit is dropped when dimensionless ("—"); "(log)" is appended for log scales.
 */
export function axisLabel(a: AxisSpec, dir: "x" | "y"): string {
  const annot: string[] = [];
  if (a.unit && a.unit !== "—") annot.push(a.unit);
  if (a.scale === "log") annot.push("log");
  const base = annot.length ? `${a.label} (${annot.join(", ")})` : a.label;
  return dir === "x" ? `${base} →` : `↑ ${base}`;
}

/** Plot scale options for one axis derived from the spec (label + scale type + grid). */
export function axis(a: AxisSpec, dir: "x" | "y"): ScaleOptions {
  return {
    label: axisLabel(a, dir),
    type: a.scale === "log" ? "log" : undefined,
    grid: true,
  };
}

/** The `{ x, y }` axis grammar for a plot, ready to spread into `Plot.plot({...})`. */
export function axes(spec: PlotSpec): { x: ScaleOptions; y: ScaleOptions } {
  return { x: axis(spec.x, "x"), y: axis(spec.y, "y") };
}
