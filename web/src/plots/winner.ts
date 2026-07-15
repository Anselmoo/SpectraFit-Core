import * as Plot from "@observablehq/plot";
import type { WinnerBar } from "../series/winner";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";

const svg = (p: any): SVGSVGElement =>
  p.tagName === "svg" ? p : p.querySelector("svg");

export function winnerPlot(
  bars: WinnerBar[],
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const ids = bars.map((b) => b.backend);
  return svg(
    Plot.plot({
      width: o.width,
      height: Math.max(120, ids.length * 30 + 40),
      marginLeft: 120,
      style: {
        background: "transparent",
        color: "var(--ink-dim)",
        fontSize: "11px",
      },
      color: {
        domain: ids,
        range: ids.map((i) => o.colors[i] ?? "var(--accent)"),
      },
      ...axes(PLOT_SPECS["winner-stability"]),
      x: { ...axes(PLOT_SPECS["winner-stability"]).x, domain: [0, 1] },
      y: { ...axes(PLOT_SPECS["winner-stability"]).y, domain: ids },
      marks: [
        Plot.barX(bars, {
          y: "backend",
          x: "fraction",
          fill: "backend",
          fillOpacity: 0.55,
        }),
      ],
    })
  );
}
