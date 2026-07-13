import * as Plot from "@observablehq/plot";
import type { WarmupLine } from "../series/warmup";
import { axes, niceDomain, dataExtent } from "./grammar";
import { PLOT_SPECS } from "./spec";
const svg=(p:any):SVGSVGElement=>(p.tagName==="svg"?p:p.querySelector("svg"));
export function warmupPlot(lines:WarmupLine[], o:{colors:Record<string,string>; width?:number}):SVGSVGElement {
  const rows=lines.flatMap(l=>l.rows); const ids=lines.map(l=>l.backend);
  const xDomain = niceDomain(dataExtent(rows.map(r=>r.n)), "log");
  return svg(Plot.plot({ width:o.width, height:220, marginLeft:52,
    style:{background:"transparent",color:"var(--ink-dim)",fontSize:"11px"},
    color:{domain:ids, range:ids.map(i=>o.colors[i]??"var(--accent)")},
    ...axes(PLOT_SPECS["warmup"]),
    x: { ...axes(PLOT_SPECS["warmup"]).x, domain: xDomain },
    marks:[ Plot.line(rows,{x:"n",y:"perRun",stroke:"backend"}) ]}));
}
