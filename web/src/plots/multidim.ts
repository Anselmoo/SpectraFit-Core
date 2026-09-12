/**
 * Multidim showcase plot (G18) — the fitted N-D surface's axis-pair projection
 * rendered as a matrix heatmap (`Plot.cell`, same primitive as the saturation
 * map). The contract's `Projection` carries only `labels` + `matrix` (no axis
 * coordinate arrays), so the axes are honest grid indices; the projected axis
 * pair is named in an in-SVG note (the `saturationHeatmap` NOTE_TEXT pattern).
 */
import * as Plot from "@observablehq/plot";
import type { Projection } from "../contract";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";
import { toSvg } from "./toSvg";

interface MatrixCell {
  i: number;
  j: number;
  v: number;
}

export function multidimProjectionHeatmap(
  proj: Projection,
  o: { width?: number },
): SVGSVGElement {
  const rows: MatrixCell[] = proj.matrix.flatMap((row, i) =>
    row.map((v, j) => ({ i, j, v })),
  );
  const nRows = proj.matrix.length;
  const noteText = `projection onto (${proj.labels[0]}, ${proj.labels[1]}) — fitted model surface`;

  const plot = Plot.plot({
    width: o.width,
    height: Math.max(180, Math.min(360, nRows * 10 + 90)),
    marginBottom: 56,
    style: { background: "transparent", color: "var(--text-secondary)", fontSize: "11px" },
    ...axes(PLOT_SPECS["multidim-projection"]),
    color: { type: "linear", scheme: "BuGn", legend: false },
    marks: [
      Plot.cell(rows, { x: "j", y: "i", fill: "v", inset: 0 }),
      Plot.text([noteText], {
        frameAnchor: "bottom-left",
        fill: "var(--text-secondary)",
        fontSize: 9,
        fontStyle: "italic",
        dy: 24,
      }),
    ],
  });

  return toSvg(plot);
}
