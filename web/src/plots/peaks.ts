import * as Plot from "@observablehq/plot";
import type { PeakRow } from "../series/peaks";
import { axes } from "./grammar";
import { PLOT_SPECS } from "./spec";
const svg=(p:any):SVGSVGElement=>(p.tagName==="svg"?p:p.querySelector("svg"));
export function peaksPlot(rows:PeakRow[], width?:number):SVGSVGElement {
  return svg(Plot.plot({ width, height:200, marginLeft:48,
    style:{background:"transparent",color:"var(--ink-dim)",fontSize:"11px"},
    ...axes(PLOT_SPECS["peaks"]),
    marks:[ Plot.areaY(rows,{x:"x",y:"y",fill:"label",fillOpacity:0.25}),
            Plot.line(rows,{x:"x",y:"y",stroke:"label",strokeWidth:1}) ]}));
}
