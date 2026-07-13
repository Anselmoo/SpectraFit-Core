import * as Plot from "@observablehq/plot";
import type { ConvLine, ThetaDistance } from "../series/convergence";
import { FLOOR_EPS } from "../series/convergence";
import { provStyle } from "../provenance";
import { axes, niceDomain, dataExtent } from "./grammar";
import { PLOT_SPECS } from "./spec";
const svg=(p:any):SVGSVGElement=>(p.tagName==="svg"?p:p.querySelector("svg"));
// Provenance grammar is RENDERED, not just dot-vs-line: reconstructed oracle
// histories carry the reconstructed opacity so the eye reads them as weaker
// evidence than the measured (real) trajectory.
const RECON_OPACITY = provStyle("reconstructed").opacity;
/** real histories => solid line; reconstructed => endpoint markers only (never a solid line). */
export function convergencePlot(lines:ConvLine[], o:{colors:Record<string,string>; width?:number}):SVGSVGElement {
  const lineRows = lines.filter(l=>l.mode==="line").flatMap(l=>l.rows);
  const endRows = lines.filter(l=>l.mode==="endpoints").flatMap(l=> l.rows.length ? [l.rows[0], l.rows[l.rows.length-1]] : []);
  const ids=lines.map(l=>l.backend);
  const allCosts = [...lineRows, ...endRows].map(r=>r.cost).filter((v): v is number => v != null);
  const yDomain = niceDomain(dataExtent(allCosts), "log");
  return svg(Plot.plot({ width:o.width, height:220, marginLeft:52,
    style:{background:"transparent",color:"var(--ink-dim)",fontSize:"11px"},
    color:{domain:ids, range:ids.map(i=>o.colors[i]??"var(--accent)")},
    ...axes(PLOT_SPECS["convergence"]),
    y: { ...axes(PLOT_SPECS["convergence"]).y, domain: yDomain },
    marks:[ Plot.line(lineRows,{x:"iter",y:"cost",stroke:"backend"}),
            Plot.dot(endRows,{x:"iter",y:"cost",stroke:"backend",r:3,symbol:"square",strokeOpacity:RECON_OPACITY,fillOpacity:RECON_OPACITY}) ]}));
}

/**
 * The REAL convergence-to-truth metric (Invariant V, Phase 4): spectrafit's
 * scale-normalized per-iteration distance dₖ = ‖(θₖ − θ_true)/s‖₂ to the known
 * synthetic truth (log-y), drawn as a line over every accepted iteration. A
 * dashed ruleY marks the recovery tolerance ("truth reached"). This is the
 * actual θ-trajectory, not the χ²-floor proxy it replaced.
 */
export function thetaDistancePlot(
  s: ThetaDistance,
  o: { colors: Record<string, string>; width?: number }
): SVGSVGElement {
  const stroke = o.colors[s.backend] ?? "var(--accent)";
  // Log y domain from dist values + FLOOR_EPS anchor (so the convergence floor is always visible)
  const allDists = s.rows.map((r) => r.dist);
  const yDomain = niceDomain(dataExtent([...allDists, FLOOR_EPS]), "log");
  return svg(
    Plot.plot({
      width: o.width,
      height: 240,
      marginLeft: 64,
      style: { background: "transparent", color: "var(--ink-dim)", fontSize: "11px" },
      ...axes(PLOT_SPECS["convergence-truth"]),
      y: { ...axes(PLOT_SPECS["convergence-truth"]).y, domain: yDomain },
      marks: [
        Plot.ruleY([s.recoveryTol], {
          stroke: "var(--ink-faint)",
          strokeDasharray: "3 3",
        }),
        Plot.line(s.rows, { x: "iter", y: "dist", stroke, strokeWidth: 1.5 }),
        Plot.dot(s.rows, { x: "iter", y: "dist", fill: stroke, r: 2.5 }),
      ],
    })
  );
}
