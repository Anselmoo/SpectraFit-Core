// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { peaksPlot } from "./peaks";
describe("peaksPlot", ()=>{
  it("renders SVG", ()=>{ expect(peaksPlot([{x:0,y:1,label:"p1"}] as any)).toBeInstanceOf(SVGElement); });
  it("empty-safe", ()=>{ expect(peaksPlot([])).toBeInstanceOf(SVGElement); });
  it("honors an explicit width", ()=>{
    const svg = peaksPlot([{x:0,y:1,label:"p1"}] as any, 360);
    expect(svg.getAttribute("width")).toBe("360");
  });
});
