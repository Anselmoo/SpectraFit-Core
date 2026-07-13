import * as Plot from "@observablehq/plot";
import type { PullEntry } from "../series/pulls";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";
const svg=(p:any):SVGSVGElement=>(p.tagName==="svg"?p:p.querySelector("svg"));
/** Histogram of pulls for non-absent backends; a dashed N(0,1)-ish band at ±1. */
export function pullsPlot(entries:PullEntry[], o:{colors:Record<string,string>; width?:number}):SVGSVGElement {
  const rows = entries.filter(e=>!e.absent).flatMap(e=>e.pulls.map(p=>({pull:p, backend:e.backend})));
  const ids=[...new Set(rows.map(r=>r.backend))];
  return svg(Plot.plot({ width:o.width, height:200, marginLeft:48, marginRight:24,
    style:{background:"transparent",color:"var(--ink-dim)",fontSize:"11px"},
    color:{domain:ids, range:ids.map(i=>o.colors[i]??"var(--accent)")},
    x:{ ...axes(PLOT_SPECS["pulls"]).x, domain:[-4,4] }, y:axes(PLOT_SPECS["pulls"]).y,
    marks:[ Plot.ruleX([-1,1],{stroke:"var(--hairline)",strokeDasharray:"3,3"}),
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            Plot.rectY(rows,Plot.binX({y:"count"},{x:"pull",fill:"backend",fillOpacity:0.5} as any)) ]}));
}
