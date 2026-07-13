// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { convergencePlot, thetaDistancePlot } from "./convergence";
import { provStyle } from "../provenance";

const RECON_OP = String(provStyle("reconstructed").opacity);
const lines=[{backend:"a",mode:"line",rows:[{iter:0,cost:10,backend:"a"},{iter:1,cost:1,backend:"a"}]},
             {backend:"b",mode:"endpoints",rows:[{iter:0,cost:9,backend:"b"},{iter:1,cost:1,backend:"b"}]}];
describe("convergencePlot",()=>{
  it("renders SVG",()=>{ expect(convergencePlot(lines as any,{colors:{a:"#0cf",b:"#f80"}})).toBeInstanceOf(SVGElement); });
  it("empty-safe",()=>{ expect(convergencePlot([],{colors:{}})).toBeInstanceOf(SVGElement); });
  it("honors an explicit width",()=>{
    const svg = convergencePlot(lines as any, {colors:{a:"#0cf",b:"#f80"}, width:560});
    expect(svg.getAttribute("width")).toBe("560");
  });
  it("renders the reconstructed provenance opacity on endpoint marks",()=>{
    const svg = convergencePlot(lines as any, {colors:{a:"#0cf",b:"#f80"}, width:560});
    expect(svg.outerHTML).toContain(`stroke-opacity="${RECON_OP}"`);
    expect(svg.outerHTML).toContain(`fill-opacity="${RECON_OP}"`);
  });
  it("labels the y-axis honestly as cost ½·χ² (log)",()=>{
    const svg = convergencePlot(lines as any, {colors:{a:"#0cf",b:"#f80"}, width:560});
    expect(svg.textContent ?? "").toContain("↑ cost ½·χ² (log)");
  });
});

const thetaSeries = {
  backend: "spectrafit",
  recoveryTol: 1e-2,
  rows: [
    { iter: 0, dist: 1.2 },
    { iter: 1, dist: 0.4 },
    { iter: 2, dist: 0.05 },
    { iter: 3, dist: 0.008 },
  ],
};
describe("thetaDistancePlot (real convergence-to-truth)", () => {
  it("renders SVG", () => {
    expect(
      thetaDistancePlot(thetaSeries as any, { colors: { spectrafit: "#0cf" } }),
    ).toBeInstanceOf(SVGElement);
  });
  it("empty-safe", () => {
    expect(
      thetaDistancePlot({ backend: "x", recoveryTol: 1e-2, rows: [] } as any, { colors: {} }),
    ).toBeInstanceOf(SVGElement);
  });
  it("honors an explicit width", () => {
    const svg = thetaDistancePlot(thetaSeries as any, { colors: { spectrafit: "#0cf" }, width: 580 });
    expect(svg.getAttribute("width")).toBe("580");
  });
  it("labels the y-axis as the scale-normalized θ-distance", () => {
    const svg = thetaDistancePlot(thetaSeries as any, { colors: { spectrafit: "#0cf" }, width: 580 });
    expect(svg.textContent ?? "").toContain("θ");
  });
});
