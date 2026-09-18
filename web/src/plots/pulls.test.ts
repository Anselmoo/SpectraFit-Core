// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { pullsPlot } from "./pulls";
const entries=[{backend:"a",pulls:[0.1,-0.2,1.3],coverage:0.66,absent:false},
               {backend:"b",pulls:[0],coverage:0,absent:true}];
describe("pullsPlot",()=>{
  it("renders SVG and excludes absent backends",()=>{ expect(pullsPlot(entries as any,{colors:{a:"#0cf"}})).toBeInstanceOf(SVGElement); });
  it("empty-safe",()=>{ expect(pullsPlot([],{colors:{}})).toBeInstanceOf(SVGElement); });
  it("honors an explicit width",()=>{
    const svg = pullsPlot(entries as any, {colors:{a:"#0cf"}, width:420});
    expect(svg.getAttribute("width")).toBe("420");
  });
});
