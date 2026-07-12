// @vitest-environment happy-dom
import { describe, it, expect, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { SuiteTable, toCsv } from "./table";
const suite = [
  { id: "EZ-001", category: "easy", m: { lmfit: { r2: 0.999, speedup: 1 }, spectrafit: { r2: 0.9995, speedup: 12 } }, winner: "spectrafit", regression: false },
  { id: "OF-001", category: "optfn", m: { lmfit: { r2: 0.41, speedup: 1 }, spectrafit: { r2: 0.35, speedup: 18 } }, winner: "lmfit", regression: false },
];
describe("SuiteTable", () => {
  it("renders a row per case with per-backend r² (subject-blind columns)", () => {
    const html = renderToStaticMarkup(<SuiteTable suite={suite as any} solverIds={["lmfit", "spectrafit"]} />);
    expect(html).toMatch(/EZ-001/); expect(html).toMatch(/OF-001/);
    expect(html).toMatch(/0\.9995/); expect(html).toMatch(/lmfit r²/);
  });
});
describe("SuiteTable selection", () => {
  it("rows carry data-case-id and are clickable when onSelect is given", () => {
    const onSelect = vi.fn();
    const html = renderToStaticMarkup(<SuiteTable suite={suite as any} solverIds={["lmfit","spectrafit"]} onSelect={onSelect} />);
    expect(html).toMatch(/data-case-id="EZ-001"/);
  });
});
describe("toCsv", () => {
  it("emits a header + one row per case (includes redChi2 + success columns)", () => {
    const csv = toCsv(suite as any, ["lmfit", "spectrafit"]);
    const lines = csv.split("\n");
    expect(lines[0]).toBe(
      "id,category,lmfit_r2,lmfit_speedup,lmfit_redChi2,lmfit_success,spectrafit_r2,spectrafit_speedup,spectrafit_redChi2,spectrafit_success,winner,regression"
    );
    expect(lines).toHaveLength(3);
    expect(lines[1]).toContain("EZ-001,easy,0.999,1");
    expect(lines[1]).toContain("spectrafit,0");
  });
});
