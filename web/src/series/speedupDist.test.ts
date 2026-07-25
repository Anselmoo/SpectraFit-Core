import { describe, it, expect } from "vitest";
import { speedupDistSeries } from "./speedupDist";

const report = {
  suite: [
    { id: "C1", m: { a: { speedup: 10 }, b: { speedup: 1 } } },
    { id: "C2", m: { a: { speedup: 20 }, b: { speedup: 2 } } },
    { id: "C3", m: { a: { speedup: 5 }, b: { speedup: 0.5 } } },
    { id: "C4", m: { a: { speedup: 15 }, b: { speedup: 1.5 } } },
    { id: "C5", m: { a: { speedup: 8 } } },
  ],
};

describe("speedupDistSeries", () => {
  it("returns one entry per backend with speedup data", () => {
    const s = speedupDistSeries(report as any, ["a", "b"]);
    expect(s.map((x) => x.backend).sort()).toEqual(["a", "b"]);
  });

  it("collects all speedup values across suite cases", () => {
    const s = speedupDistSeries(report as any, ["a"]);
    const a = s.find((x) => x.backend === "a")!;
    expect(a.values.sort((x, y) => x - y)).toEqual([5, 8, 10, 15, 20]);
  });

  it("computes median/p25/p75/p5/p95 quartiles per backend", () => {
    const s = speedupDistSeries(report as any, ["a"]);
    const a = s[0];
    // sorted a = [5, 8, 10, 15, 20] → median = 10
    expect(a.median).toBe(10);
    expect(a.p5).toBeLessThanOrEqual(a.p25);
    expect(a.p25).toBeLessThanOrEqual(a.median);
    expect(a.median).toBeLessThanOrEqual(a.p75);
    expect(a.p75).toBeLessThanOrEqual(a.p95);
  });

  it("all quartiles are positive (speedup > 0 invariant)", () => {
    const s = speedupDistSeries(report as any, ["a", "b"]);
    for (const box of s) {
      expect(box.p5).toBeGreaterThan(0);
      expect(box.median).toBeGreaterThan(0);
      expect(box.p95).toBeGreaterThan(0);
    }
  });

  it("omits backends with no speedup data", () => {
    const s = speedupDistSeries(report as any, ["a", "missing"]);
    expect(s.find((x) => x.backend === "missing")).toBeUndefined();
  });

  it("filters non-finite and non-positive speedups", () => {
    const bad = {
      suite: [
        { id: "X1", m: { a: { speedup: 5 } } },
        { id: "X2", m: { a: { speedup: NaN } } },
        { id: "X3", m: { a: { speedup: -1 } } },
        { id: "X4", m: { a: { speedup: Infinity } } },
      ],
    };
    const s = speedupDistSeries(bad as any, ["a"]);
    expect(s[0].values).toEqual([5]);
  });
});
