import { describe, it, expect } from "vitest";
import { OVERALL_PANELS, SINGLE_PANELS, EVIDENCE_PANELS } from "./evidenceScope";

describe("evidence scope registry", () => {
  it("overall and single are disjoint", () => {
    const overlap = OVERALL_PANELS.filter((p) => (SINGLE_PANELS as readonly string[]).includes(p));
    expect(overlap).toEqual([]);
  });
  it("every known panel has exactly one scope", () => {
    expect([...EVIDENCE_PANELS].sort()).toEqual([...OVERALL_PANELS, ...SINGLE_PANELS].sort());
  });
  it("the all-cases panels are overall, the drill-down panels are single", () => {
    expect(OVERALL_PANELS).toContain("suite-table");
    expect(OVERALL_PANELS).toContain("saturation");
    expect(SINGLE_PANELS).toContain("fit");
    expect(SINGLE_PANELS).toContain("conditioning");
    expect(SINGLE_PANELS).not.toContain("suite-table");
  });
});
