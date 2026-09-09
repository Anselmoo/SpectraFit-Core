import { describe, it, expect } from "vitest";
import { performanceProfileSeries } from "./performanceProfile";

// Two backends over three cases. Costs (medMs):
//   C1: a=10, b=5   → min 5  → r: a=2,   b=1
//   C2: a=2,  b=8   → min 2  → r: a=1,   b=4
//   C3: a=20, b=4   → min 4  → r: a=5,   b=1
// a is fastest on 1/3 (C2); b is fastest on 2/3 (C1,C3).
const report = {
  suite: [
    { id: "C1", category: "easy", m: { a: { medMs: 10 }, b: { medMs: 5 } } },
    { id: "C2", category: "easy", m: { a: { medMs: 2 }, b: { medMs: 8 } } },
    { id: "C3", category: "hard", m: { a: { medMs: 20 }, b: { medMs: 4 } } },
  ],
};

describe("performanceProfileSeries", () => {
  it("returns one step series per backend, each as {tau, rho} points", () => {
    const s = performanceProfileSeries(report as any, ["a", "b"]);
    expect(s.map((x) => x.backend).sort()).toEqual(["a", "b"]);
    for (const series of s) {
      for (const pt of series.points) {
        expect(typeof pt.tau).toBe("number");
        expect(typeof pt.rho).toBe("number");
        expect(pt.tau).toBeGreaterThanOrEqual(1);
      }
    }
  });

  it("rho is monotone non-decreasing in tau", () => {
    const s = performanceProfileSeries(report as any, ["a", "b"]);
    for (const series of s) {
      for (let i = 1; i < series.points.length; i++) {
        expect(series.points[i].rho).toBeGreaterThanOrEqual(series.points[i - 1].rho);
        expect(series.points[i].tau).toBeGreaterThanOrEqual(series.points[i - 1].tau);
      }
    }
  });

  it("rho(1) equals the fastest-fraction for each backend", () => {
    const s = performanceProfileSeries(report as any, ["a", "b"]);
    const rhoAt = (backend: string, tau: number) => {
      const pts = s.find((x) => x.backend === backend)!.points.filter((p) => p.tau <= tau + 1e-12);
      return pts.length ? pts[pts.length - 1].rho : 0;
    };
    // a fastest on 1/3, b on 2/3
    expect(rhoAt("a", 1)).toBeCloseTo(1 / 3, 10);
    expect(rhoAt("b", 1)).toBeCloseTo(2 / 3, 10);
  });

  it("rho never exceeds 1 (the right plateau is <= 1)", () => {
    const s = performanceProfileSeries(report as any, ["a", "b"]);
    for (const series of s) {
      for (const pt of series.points) expect(pt.rho).toBeLessThanOrEqual(1 + 1e-12);
    }
  });

  it("a solver fastest on every case has rho(1) = 1", () => {
    const dominant = {
      suite: [
        { id: "C1", category: "easy", m: { a: { medMs: 1 }, b: { medMs: 9 } } },
        { id: "C2", category: "easy", m: { a: { medMs: 1 }, b: { medMs: 9 } } },
      ],
    };
    const s = performanceProfileSeries(dominant as any, ["a", "b"]);
    const a = s.find((x) => x.backend === "a")!;
    expect(a.points[0].tau).toBe(1);
    expect(a.points[0].rho).toBe(1);
  });

  it("skips a backend with no measured cost for a case (no NaN ratios)", () => {
    const sparse = {
      suite: [{ id: "C1", category: "easy", m: { a: { medMs: 4 } } }],
    };
    const s = performanceProfileSeries(sparse as any, ["a", "b"]);
    const b = s.find((x) => x.backend === "b")!;
    // b solved nothing → its profile is flat at rho 0
    for (const pt of b.points) expect(pt.rho).toBe(0);
  });
});
