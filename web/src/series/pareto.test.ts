import { describe, it, expect } from "vitest";
import { paretoSeries } from "./pareto";

const report = {
  suite: [
    { id: "C1", category: "easy", m: { a: { medMs: 10, r2: 0.99 }, b: { medMs: 5, r2: 0.90 } } },
    { id: "C2", category: "easy", m: { a: { medMs: 2, r2: 0.999 }, b: { medMs: 8, r2: 0.95 } } },
    { id: "C3", category: "hard", m: { a: { medMs: 20, r2: 0.80 }, b: { medMs: 4, r2: 0.999 } } },
  ],
};

describe("paretoSeries", () => {
  it("returns one series per backend over all suite cases", () => {
    const s = paretoSeries(report as any, ["a", "b"]);
    expect(s.map((x) => x.backend).sort()).toEqual(["a", "b"]);
    expect(s.find((x) => x.backend === "a")!.points).toHaveLength(3);
  });

  it("carries x=medMs, y=r2, caseId per point", () => {
    const a = paretoSeries(report as any, ["a"])[0];
    const c2 = a.points.find((p) => p.caseId === "C2")!;
    expect(c2.x).toBe(2);
    expect(c2.y).toBe(0.999);
  });

  it("computes a non-dominated envelope (lower medMs AND higher r2), monotone in x", () => {
    const s = paretoSeries(report as any, ["a", "b"]);
    // envelope points sorted by ascending x; r2 strictly increasing along the frontier
    for (let i = 1; i < s.envelope.length; i++) {
      expect(s.envelope[i].x).toBeGreaterThanOrEqual(s.envelope[i - 1].x);
      expect(s.envelope[i].y).toBeGreaterThan(s.envelope[i - 1].y);
    }
    // the cheapest-and-best point (C2/a: 2ms, r2 .999) must be on the frontier
    expect(s.envelope.some((p) => p.caseId === "C2" && p.backend === "a")).toBe(true);
  });

  it("skips a backend with no metric for a case (no NaN points)", () => {
    const sparse = { suite: [{ id: "C1", category: "easy", m: { a: { medMs: 1, r2: 0.5 } } }] };
    const s = paretoSeries(sparse as any, ["a", "b"]);
    expect(s.find((x) => x.backend === "b")!.points).toEqual([]);
  });
});
