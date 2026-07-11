import { describe, it, expect } from "vitest";
import { harmonicMean, harmonicMeanFromSuite } from "./harmonicMeanSpeedup";

// ---------------------------------------------------------------------------
// harmonicMean unit tests
// ---------------------------------------------------------------------------

describe("harmonicMean", () => {
  it("closed form: HM([12, 18]) = 2/(1/12+1/18) = 14.4", () => {
    const result = harmonicMean([12, 18]);
    expect(result).toBeCloseTo(14.4, 10);
  });

  it("closed form: HM([1, 2, 4, 4]) = 4/(1+0.5+0.25+0.25) = 2.0", () => {
    expect(harmonicMean([1, 2, 4, 4])).toBeCloseTo(2.0, 10);
  });

  it("single value returns itself", () => {
    expect(harmonicMean([7.5])).toBeCloseTo(7.5, 10);
  });

  it("equal values return that value", () => {
    expect(harmonicMean([5, 5, 5])).toBeCloseTo(5.0, 10);
  });

  it("empty array returns null", () => {
    expect(harmonicMean([])).toBeNull();
  });

  it("filters NaN and non-positive values", () => {
    // Only [4] is valid; HM([4]) = 4
    const result = harmonicMean([4, NaN, -1, 0, Infinity]);
    expect(result).toBeCloseTo(4.0, 10);
  });

  it("returns null when all values are non-positive/non-finite", () => {
    expect(harmonicMean([NaN, -1, 0])).toBeNull();
  });

  it("HM ≤ geomean for positively-skewed data (AM-HM inequality)", () => {
    // [2, 8, 32]: geomean = 8.0; HM = 3/(0.5+0.125+0.03125) ≈ 4.571
    const hm = harmonicMean([2, 8, 32])!;
    const gm = Math.exp(Math.log(2) + Math.log(8) + Math.log(32)) ** (1 / 3);
    expect(hm).toBeLessThanOrEqual(gm + 1e-10); // HM ≤ GM
  });
});

// ---------------------------------------------------------------------------
// harmonicMeanFromSuite unit tests
// ---------------------------------------------------------------------------

const SUITE = [
  { id: "C1", m: { sf: { speedup: 12 }, lm: { speedup: 1 } } },
  { id: "C2", m: { sf: { speedup: 18 }, lm: { speedup: 1 } } },
  { id: "C3", m: { sf: { speedup: 6 } } }, // no lm entry
];

describe("harmonicMeanFromSuite", () => {
  it("computes HM of sf speedups = 2/(1/12+1/18) from the suite row", () => {
    // C3 also contributes sf.speedup=6 → HM([12,18,6]) = 3/(1/12+1/18+1/6)
    // = 3 / (0.0833+0.0556+0.1667) = 3 / 0.3056 ≈ 9.818…
    const result = harmonicMeanFromSuite(SUITE as any, "sf");
    // verify it's a number and roughly matches manual calc
    expect(result).not.toBeNull();
    const expected = 3 / (1 / 12 + 1 / 18 + 1 / 6);
    expect(result!).toBeCloseTo(expected, 8);
  });

  it("returns null for a subject id with no speedup data", () => {
    expect(harmonicMeanFromSuite(SUITE as any, "missing")).toBeNull();
  });

  it("returns null for an empty suite", () => {
    expect(harmonicMeanFromSuite([], "sf")).toBeNull();
  });

  it("filters non-finite speedup values", () => {
    const badSuite = [
      { m: { sf: { speedup: 4 } } },
      { m: { sf: { speedup: NaN } } },
      { m: { sf: { speedup: -1 } } },
    ];
    // Only [4] is valid
    expect(harmonicMeanFromSuite(badSuite as any, "sf")).toBeCloseTo(4.0, 10);
  });
});
