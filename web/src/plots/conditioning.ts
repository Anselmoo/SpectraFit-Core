import * as Plot from "@observablehq/plot";
import type { KappaRow } from "../series/conditioning";
import { axes, niceDomain, dataExtent } from "./grammar";
import { PLOT_SPECS } from "./spec";

const svg = (p: any): SVGSVGElement =>
  p.tagName === "svg" ? p : p.querySelector("svg");

export function conditioningPlot(
  rows: KappaRow[],
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const present = rows.filter((r) => r.kappa != null) as (KappaRow & {
    kappa: number;
  })[];
  const absent = rows.filter((r) => r.absent);
  // Every backend keeps a row — absent ones are rendered as an explicit greyed
  // lane ("κ(J) not exposed") rather than silently dropped, so the eye reads a
  // capability gap, not a missing solver. Domain is ALL backends, in order.
  const allIds = rows.map((r) => r.backend);
  // Anchor the absent label at the low end of the present κ range (or 1 when no
  // backend exposes κ) so it sits inside the log axis without distorting it.
  const presentMin = present.length ? Math.min(...present.map((r) => r.kappa)) : 1;
  const absentRows = absent.map((r) => ({ backend: r.backend, x: presentMin }));
  // Include the ill-posed threshold (1e6) so it is always visible in the domain
  const xDomain = niceDomain(dataExtent([1e6, ...present.map((r) => r.kappa)]), "log");
  return svg(
    Plot.plot({
      width: o.width,
      height: Math.max(120, allIds.length * 30 + 40),
      marginLeft: 96,
      style: {
        background: "transparent",
        color: "var(--ink-dim)",
        fontSize: "11px",
      },
      color: {
        domain: present.map((r) => r.backend),
        range: present.map((r) => o.colors[r.backend] ?? "var(--accent)"),
      },
      x: { ...axes(PLOT_SPECS["conditioning"]).x, domain: xDomain },
      y: { ...axes(PLOT_SPECS["conditioning"]).y, domain: allIds },
      marks: [
        // κ ill-posed threshold (κ ≥ 1e6). Drawn first so dots sit on top.
        Plot.ruleX([1e6], { stroke: "var(--fail)", strokeDasharray: "3,3" }),
        // A dot per backend at its κ(J). NOTE: barX is unusable here — a bar needs
        // a 0 baseline, which a log scale has no representation for, so bars never
        // render. A dot's position on the log axis conveys the magnitude directly.
        Plot.dot(present, {
          y: "backend",
          x: "kappa",
          fill: "backend",
          stroke: "backend",
          r: 5,
        }),
        // Absent backends: a greyed "not exposed" label on their own lane.
        Plot.text(absentRows, {
          y: "backend",
          x: "x",
          text: () => "κ(J) not exposed",
          fill: "var(--ink-faint)",
          fontStyle: "italic",
          dx: 6,
          textAnchor: "start",
        }),
      ],
    })
  );
}
