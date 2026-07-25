// @vitest-environment happy-dom
import { describe, it, expect } from "vitest";
import { saturationHeatmap } from "./saturation";
const rows = [
  { category: "easy", backend: "lmfit", r2: 0.999, failed: false },
  { category: "optfn", backend: "lmfit", r2: 0.4, failed: true },
];
describe("saturationHeatmap", () => {
  it("renders an SVG from grid rows", () => {
    const el = saturationHeatmap(rows, {});
    expect(el).toBeInstanceOf(SVGElement);
    expect(el.querySelectorAll("*").length).toBeGreaterThan(0);
  });
  it("is empty-safe", () => {
    expect(saturationHeatmap([], {})).toBeInstanceOf(SVGElement);
  });
  it("honors an explicit width", () => {
    const el = saturationHeatmap(rows, { width: 380 });
    expect(el.getAttribute("width")).toBe("380");
  });
  it("annotates category y-axis labels with (N=…) when categoryCounts provided", () => {
    const el = saturationHeatmap(rows, { categoryCounts: { easy: 42, optfn: 7 } });
    const text = el.textContent ?? "";
    expect(text).toContain("(N=42)");
    expect(text).toContain("(N=7)");
  });
  it("failed cells (r²<0.9) are rendered in a distinct fill color from agree-band cells", () => {
    // Construct rows: one divergent (r²≈0.3, failed=true) and one near-perfect (r²≈0.95, failed=false).
    // The pre-fix code clamped both to the same floor — post-fix the failed cell must carry
    // the --fail CSS variable as its fill, visually distinct from the BuGn agree-band.
    const mixedRows = [
      { category: "edge", backend: "lmfit", r2: 0.3, failed: true },
      { category: "easy", backend: "lmfit", r2: 0.95, failed: false },
    ];
    const el = saturationHeatmap(mixedRows, {});
    // Observable Plot sets fill on the <g aria-label="cell"> wrapper, not on individual
    // <rect> children. Check the full innerHTML for the --fail token.
    const html = el.innerHTML;
    expect(html).toContain("var(--fail)");
  });
  it("shows a scale cue noting the 0.9 color floor", () => {
    // A minimal caption/note must be present so a reader knows 0.9 is the floor,
    // not zero. The exact text may vary, but it must mention "0.9".
    const mixedRows = [
      { category: "edge", backend: "lmfit", r2: 0.3, failed: true },
      { category: "easy", backend: "lmfit", r2: 0.95, failed: false },
    ];
    const el = saturationHeatmap(mixedRows, {});
    const text = el.textContent ?? "";
    expect(text).toContain("0.9");
  });
});
