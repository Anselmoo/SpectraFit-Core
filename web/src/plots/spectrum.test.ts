// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { spectrumPlot, residualPlot } from "./spectrum";
const s = { ref: [{x:0,y:1}], guess: [{x:0,y:0.9}], fits: [{ backend:"lmfit", rows:[{x:0,y:1,backend:"lmfit"}] }] };
describe("spectrum plots", () => {
  it("spectrumPlot renders an SVG", () => {
    expect(spectrumPlot(s as any, { colors: { lmfit: "#0cf" } })).toBeInstanceOf(SVGElement);
  });
  it("residualPlot renders an SVG and is empty-safe", () => {
    expect(residualPlot([], { colors: {} })).toBeInstanceOf(SVGElement);
  });
  it("spectrumPlot honors an explicit width", () => {
    const svg = spectrumPlot(s as any, { colors: {}, width: 320 });
    expect(svg.getAttribute("width")).toBe("320");
  });
  it("residualPlot honors an explicit width", () => {
    const svg = residualPlot([], { colors: {}, width: 400 });
    expect(svg.getAttribute("width")).toBe("400");
  });
});
