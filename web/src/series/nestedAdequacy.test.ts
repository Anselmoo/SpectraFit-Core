import { describe, it, expect } from "vitest";
import { nestedVerdict, deltaRows } from "./nestedAdequacy";
import type { NestedAdequacy } from "./nestedAdequacy";

// ---------------------------------------------------------------------------
// Fixture: tri-Gaussian featured case — BIC recovers, AIC over-selects.
// Mirrors the contract docstring comment in openapi.gen.ts.
// ---------------------------------------------------------------------------
const FIXTURE: NestedAdequacy = {
  trueOrder: 3,
  reducedRejected: true,
  overNotPreferredAic: false,  // AIC selects the 4-peak model (over-selects)
  overNotPreferredBic: true,   // BIC correctly prefers the true 3-peak model
  selectedOrderAic: 4,
  selectedOrderBic: 3,
  recoveredTrueOrderAic: false,
  recoveredTrueOrderBic: true,
  reducedVsTrue: { lrtStat: 18.5, lrtP: 0.0002, fStat: 16.2, fP: 0.0003, dAIC: -14.5, dBIC: -12.1 },
  trueVsOver:   { lrtStat:  3.1, lrtP:  0.079,  fStat:  2.8, fP: 0.098,  dAIC:  1.2,  dBIC:   3.8 },
};

describe("nestedVerdict", () => {
  it("returns null for null/undefined input", () => {
    expect(nestedVerdict(null)).toBeNull();
    expect(nestedVerdict(undefined)).toBeNull();
  });

  it("derives trueOrder and BIC-governed recovery", () => {
    const v = nestedVerdict(FIXTURE)!;
    expect(v.trueOrder).toBe(3);
    expect(v.bicRecovered).toBe(true);
    expect(v.selectedOrderBic).toBe(3);
  });

  it("derives AIC result (over-selects in this fixture)", () => {
    const v = nestedVerdict(FIXTURE)!;
    expect(v.aicRecovered).toBe(false);
    expect(v.selectedOrderAic).toBe(4);
  });

  it("flags AIC/BIC disagreement when orders differ", () => {
    const v = nestedVerdict(FIXTURE)!;
    expect(v.aicBicAgree).toBe(false);
  });

  it("flags AIC/BIC agreement when orders are the same", () => {
    const agreeFixture: NestedAdequacy = { ...FIXTURE, selectedOrderAic: 3, recoveredTrueOrderAic: true };
    const v = nestedVerdict(agreeFixture)!;
    expect(v.aicBicAgree).toBe(true);
  });

  it("carries reducedRejected and LRT p-value", () => {
    const v = nestedVerdict(FIXTURE)!;
    expect(v.reducedRejected).toBe(true);
    expect(v.lrtPReducedVsTrue).toBeCloseTo(0.0002);
  });

  it("carries ΔAIC / ΔBIC for both comparisons", () => {
    const v = nestedVerdict(FIXTURE)!;
    expect(v.dAICReducedVsTrue).toBeCloseTo(-14.5);
    expect(v.dBICReducedVsTrue).toBeCloseTo(-12.1);
    expect(v.dAICTrueVsOver).toBeCloseTo(1.2);
    expect(v.dBICTrueVsOver).toBeCloseTo(3.8);
  });
});

describe("deltaRows", () => {
  it("returns empty array for null input", () => {
    expect(deltaRows(null)).toEqual([]);
    expect(deltaRows(undefined)).toEqual([]);
  });

  it("returns two rows (reduced-vs-true, true-vs-over)", () => {
    const rows = deltaRows(FIXTURE);
    expect(rows).toHaveLength(2);
  });

  it("first row is reduced-vs-true with correct values", () => {
    const row = deltaRows(FIXTURE)[0];
    expect(row.label).toContain("true");
    expect(row.label).toContain("reduced");
    expect(row.lrtP).toBeCloseTo(0.0002);
    expect(row.dAIC).toBeCloseTo(-14.5);
    expect(row.dBIC).toBeCloseTo(-12.1);
  });

  it("second row is true-vs-over with correct values", () => {
    const row = deltaRows(FIXTURE)[1];
    expect(row.label).toContain("over");
    expect(row.lrtP).toBeCloseTo(0.079);
    expect(row.dAIC).toBeCloseTo(1.2);
    expect(row.dBIC).toBeCloseTo(3.8);
  });

  it("row labels include the three order values (m*-1, m*, m*+1)", () => {
    const rows = deltaRows(FIXTURE);
    // true order 3 → reduced 2, over 4
    expect(rows[0].label).toContain("3");
    expect(rows[0].label).toContain("2");
    expect(rows[1].label).toContain("3");
    expect(rows[1].label).toContain("4");
  });
});
