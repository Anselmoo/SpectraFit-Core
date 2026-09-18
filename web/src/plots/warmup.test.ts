// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { warmupPlot } from "./warmup";
const lines=[{backend:"jax",coldMs:100,hotMs:2,rows:[{n:1,perRun:100,backend:"jax"},{n:2,perRun:51,backend:"jax"}]}];
describe("warmupPlot",()=>{
  it("renders SVG",()=>{ expect(warmupPlot(lines as any,{colors:{jax:"#0cf"}})).toBeInstanceOf(SVGElement); });
  it("empty-safe",()=>{ expect(warmupPlot([],{colors:{}})).toBeInstanceOf(SVGElement); });
  it("honors an explicit width",()=>{
    const svg = warmupPlot(lines as any, {colors:{jax:"#0cf"}, width:600});
    expect(svg.getAttribute("width")).toBe("600");
  });
});
