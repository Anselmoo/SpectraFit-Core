import { describe, it, expect } from "vitest";
import { recoveryErrorSeries, quantileSorted } from "./recoveryError";

describe("quantileSorted", () => {
  const xs = [1, 2, 3, 4, 5]; // already sorted
  it("returns endpoints at q=0 and q=1", () => {
    expect(quantileSorted(xs, 0)).toBe(1);
    expect(quantileSorted(xs, 1)).toBe(5);
  });
  it("returns the median at q=0.5", () => {
    expect(quantileSorted(xs, 0.5)).toBe(3);
    expect(quantileSorted([1, 2, 3, 4], 0.5)).toBe(2.5); // interpolated
  });
  it("interpolates linearly between samples", () => {
    expect(quantileSorted([0, 10], 0.25)).toBe(2.5);
  });
  it("empty → NaN", () => {
    expect(Number.isNaN(quantileSorted([], 0.5))).toBe(true);
  });
});

const report = {
  suite: [
    { id: "C1", category: "a", m: { sf: { paramErr: 1 }, lm: { paramErr: 10 } } },
    { id: "C2", category: "a", m: { sf: { paramErr: 3 }, lm: { paramErr: 20 } } },
    { id: "C3", category: "b", m: { sf: { paramErr: 2 }, lm: { paramErr: 30 } } },
  ],
};

describe("recoveryErrorSeries", () => {
  it("collects the paramErr array per backend over all cases", () => {
    const s = recoveryErrorSeries(report as any, ["sf", "lm"]);
    expect(s.find((b) => b.backend === "sf")!.values.sort((x, y) => x - y)).toEqual([1, 2, 3]);
    expect(s.find((b) => b.backend === "lm")!.values.sort((x, y) => x - y)).toEqual([10, 20, 30]);
  });

  it("computes median/p25/p75/p5/p95 quartiles per backend", () => {
    const s = recoveryErrorSeries(report as any, ["sf"])[0];
    // sorted sf = [1,2,3] → median 2
    expect(s.median).toBe(2);
    expect(s.p5).toBeLessThanOrEqual(s.p25);
    expect(s.p25).toBeLessThanOrEqual(s.median);
    expect(s.median).toBeLessThanOrEqual(s.p75);
    expect(s.p75).toBeLessThanOrEqual(s.p95);
  });

  it("skips non-finite paramErr and omits a backend with no values", () => {
    const sparse = { suite: [{ id: "C1", category: "a", m: { sf: { paramErr: 5 } } }] };
    const s = recoveryErrorSeries(sparse as any, ["sf", "lm"]);
    expect(s.find((b) => b.backend === "lm")).toBeUndefined();
    expect(s.find((b) => b.backend === "sf")!.values).toEqual([5]);
  });
});
