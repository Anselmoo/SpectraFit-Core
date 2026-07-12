import * as Plot from "@observablehq/plot";
import type { QQBackend } from "../series/residualQQ";
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
 * QQ plot of standardised residuals vs theoretical normal quantiles.
 * One colored dot series per backend; the y = x reference line shows
 * where perfectly Gaussian residuals would fall.
 */
export function residualQQPlot(
  series: QQBackend[],
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const ids = series.map((s) => s.backend);
  const dots = series.flatMap((s) => s.points.map((p) => ({ ...p, backend: s.backend })));

  // Reference line: y = x through the range of theoretical quantiles
  const allTheoretical = dots.map((d) => d.theoretical).filter(Number.isFinite);
  const xMin = allTheoretical.length > 0 ? Math.min(...allTheoretical) : -3;
  const xMax = allTheoretical.length > 0 ? Math.max(...allTheoretical) : 3;
  const refLine = [
    { theoretical: xMin, sample: xMin },
    { theoretical: xMax, sample: xMax },
  ];

  return unwrapSvg(
    Plot.plot({
      width: o.width,
      height: 320,
      marginLeft: 56,
      marginRight: 24,
      marginBottom: 48,
      style: { background: "transparent", color: "var(--ink-dim)", fontSize: "11px" },
      color: { domain: ids, range: ids.map((i) => o.colors[i] ?? "var(--accent)") },
      ...axes(PLOT_SPECS["residual-qq"]),
      marks: [
        // Reference diagonal y = x
        Plot.line(refLine, {
          x: "theoretical",
          y: "sample",
          stroke: "var(--ink-faint)",
          strokeWidth: 1,
          strokeDasharray: "4 3",
        }),
        // Per-backend dots
        Plot.dot(dots, {
          x: "theoretical",
          y: "sample",
          stroke: "backend",
          fill: "backend",
          fillOpacity: 0.5,
          r: 2.5,
        }),
      ],
    })
  );
}
