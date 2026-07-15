/**
 * Global-fit showcase plots (G18) — one shared model jointly fitted across a
 * multi-dataset series (`GlobalFitGraph`).
 *
 *  - `globalFitSlicesPlot`: every slice's observed points (dots) + the joint
 *    model curve (line), colored sequentially by the slice's dataset-axis
 *    coordinate — the "one model, many spectra" picture.
 *  - `globalFitKineticsPlot`: each shared peak's amplitude trace along the
 *    dataset axis — the per-slice kinetics the joint fit recovers while the
 *    peak centers/widths stay shared.
 */
import * as Plot from "@observablehq/plot";
import type { GlobalFit } from "../contract";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";

interface SliceRow {
  x: number;
  y: number;
  coord: number;
}

interface TraceRow {
  t: number;
  amplitude: number;
  peak: string;
}

function toSvg(plot: (SVGSVGElement | HTMLElement) & { querySelector?: (s: string) => Element | null }): SVGSVGElement {
  if (plot instanceof SVGSVGElement) return plot;
  const svg = plot.querySelector?.("svg");
  if (svg instanceof SVGSVGElement) return svg;
  return plot as unknown as SVGSVGElement;
}

export function globalFitSlicesPlot(gf: GlobalFit, o: { width?: number }): SVGSVGElement {
  const obsRows: SliceRow[] = gf.slices.flatMap((s) =>
    gf.x.map((xv, k) => ({ x: xv, y: s.obs[k], coord: s.coord })),
  );
  const modelRows: SliceRow[] = gf.slices.flatMap((s) =>
    gf.x.map((xv, k) => ({ x: xv, y: s.model[k], coord: s.coord })),
  );

  return toSvg(
    Plot.plot({
      width: o.width,
      height: 260,
      style: { background: "transparent", color: "var(--ink-dim)", fontSize: "11px" },
      ...axes(PLOT_SPECS["global-fit-slices"]),
      color: { type: "linear", scheme: "BuGn", legend: false },
      marks: [
        Plot.dot(obsRows, { x: "x", y: "y", fill: "coord", r: 1.2, fillOpacity: 0.45 }),
        Plot.line(modelRows, { x: "x", y: "y", stroke: "coord", z: "coord", strokeWidth: 1.6 }),
        Plot.text(
          [`${gf.slices.length} slices along ${gf.axisLabel} — shared centers/widths, one joint fit`],
          { frameAnchor: "top-right", fill: "var(--ink-faint)", fontSize: 9, fontStyle: "italic", dy: 4 },
        ),
      ],
    }),
  );
}

export function globalFitKineticsPlot(gf: GlobalFit, o: { width?: number }): SVGSVGElement {
  const rows: TraceRow[] = gf.traces.flatMap((t) =>
    gf.datasetAxis.map((tv, k) => ({ t: tv, amplitude: t.amplitude[k], peak: t.label })),
  );

  return toSvg(
    Plot.plot({
      width: o.width,
      height: 200,
      style: { background: "transparent", color: "var(--ink-dim)", fontSize: "11px" },
      ...axes(PLOT_SPECS["global-fit-kinetics"]),
      color: { type: "ordinal", scheme: "BuGn", legend: false },
      marks: [
        Plot.line(rows, { x: "t", y: "amplitude", stroke: "peak", z: "peak", strokeWidth: 1.6, marker: "circle" }),
        Plot.text(
          rows.filter((r) => r.t === gf.datasetAxis[gf.datasetAxis.length - 1]),
          { x: "t", y: "amplitude", text: "peak", fill: "var(--ink-faint)", fontSize: 9, dx: 6, textAnchor: "start" },
        ),
      ],
    }),
  );
}
