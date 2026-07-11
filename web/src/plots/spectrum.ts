/**
 * Spectrum + residual Observable Plot factories.
 * Colors via CSS vars / caller-supplied color map; no hardcoded backend ids.
 * SVG-unwrap pattern matches ciIntervalPlot exactly.
 */
import * as Plot from "@observablehq/plot";
import type { SpectrumSeries, XY } from "../series/spectrum";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";

/** Normalise Plot.plot output to always return an SVGSVGElement. */
const unwrapSvg = (p: any): SVGSVGElement => {
  if (p instanceof SVGSVGElement) return p;
  const found = p.querySelector?.("svg");
  if (found instanceof SVGSVGElement) return found;
  return p as unknown as SVGSVGElement;
};

/**
 * Spectrum overlay: reference data as markers, initial guess as a dashed line,
 * each backend's fitted curve as a solid colored line.
 */
export function spectrumPlot(
  s: SpectrumSeries,
  o: { colors: Record<string, string>; width?: number },
): SVGSVGElement {
  const allFits = s.fits.flatMap((f) => f.rows);
  const ids = s.fits.map((f) => f.backend);
  return unwrapSvg(
    Plot.plot({
      width: o.width,
      height: 300,
      marginLeft: 48,
      marginBottom: 36,
      style: { background: "transparent", color: "var(--ink-dim)", fontSize: "11px" },
      ...axes(PLOT_SPECS["spectrum"]),
      color: {
        domain: ids,
        range: ids.map((id) => o.colors[id] ?? "var(--accent)"),
      },
      marks: [
        // reference DATA = markers (spectrum_marker_convention: data has markers, fits are lines)
        Plot.dot(s.ref, { x: "x", y: "y", r: 1.6, fill: "var(--ink-dim)", fillOpacity: 0.55 }),
        // initial guess = dashed line
        Plot.line(s.guess, { x: "x", y: "y", stroke: "var(--prov-derived)", strokeDasharray: "3,3" }),
        // each backend's fitted curve = solid colored line
        Plot.line(allFits, { x: "x", y: "y", stroke: "backend", strokeWidth: 1.5 }),
      ],
    }),
  );
}

/**
 * Residuals strip — small horizontal strip below the spectrum overlay.
 * Empty-safe: renders a baseline rule even with no rows.
 */
/* Ive: residual strip height — content-derived, readable (was crushed) */
const RESIDUAL_HEIGHT = 120;

export function residualPlot(
  rows: Array<XY & { backend: string }>,
  o: { colors: Record<string, string>; width?: number },
): SVGSVGElement {
  const ids = [...new Set(rows.map((r) => r.backend))];
  return unwrapSvg(
    Plot.plot({
      width: o.width,
      height: RESIDUAL_HEIGHT,
      marginLeft: 48,
      marginBottom: 30,
      style: { background: "transparent", color: "var(--ink-dim)", fontSize: "11px" },
      ...axes(PLOT_SPECS["residual"]),
      color: {
        domain: ids,
        range: ids.map((id) => o.colors[id] ?? "var(--accent)"),
      },
      marks: [
        Plot.ruleY([0], { stroke: "var(--hairline)" }),
        Plot.line(rows, { x: "x", y: "y", stroke: "backend", strokeOpacity: 0.7 }),
      ],
    }),
  );
}
