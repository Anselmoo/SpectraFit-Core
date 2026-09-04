import { describe, it, expect } from "vitest";
import { invNormalCdf, residualQQSeries } from "./residualQQ";

// ---------------------------------------------------------------------------
// invNormalCdf unit tests
// ---------------------------------------------------------------------------

describe("invNormalCdf", () => {
  it("returns 0 at p=0.5 (median of standard normal)", () => {
    expect(invNormalCdf(0.5)).toBeCloseTo(0, 3);
  });

  it("returns ~1.96 at p=0.975 (95% two-tailed critical value)", () => {
    expect(invNormalCdf(0.975)).toBeCloseTo(1.96, 2);
  });

  it("returns ~-1.96 at p=0.025 (symmetric lower tail)", () => {
    expect(invNormalCdf(0.025)).toBeCloseTo(-1.96, 2);
  });

  it("returns ~1.645 at p=0.95 (one-tailed 5% critical value)", () => {
    expect(invNormalCdf(0.95)).toBeCloseTo(1.645, 2);
  });

  it("returns ~-2.576 at p=0.005 (lower extreme tail)", () => {
    expect(invNormalCdf(0.005)).toBeCloseTo(-2.576, 1);
  });

  it("returns -Infinity at p=0", () => {
    expect(invNormalCdf(0)).toBe(-Infinity);
  });

  it("returns +Infinity at p=1", () => {
    expect(invNormalCdf(1)).toBe(Infinity);
  });

  it("is antisymmetric: invNormalCdf(p) = -invNormalCdf(1-p)", () => {
    for (const p of [0.1, 0.2, 0.3, 0.4]) {
      expect(invNormalCdf(p)).toBeCloseTo(-invNormalCdf(1 - p), 4);
    }
  });
});

// ---------------------------------------------------------------------------
// residualQQSeries unit tests
// ---------------------------------------------------------------------------

const residuals = [0.1, -0.2, 0.3, -0.4, 0.5, -0.6, 0.7, -0.8, 0.9, -1.0];

const report = {
  analyzed: [
    {
      id: "C1",
      category: "easy",
      profiles: {
        a: { fit: { resid: residuals } },
        b: { fit: { resid: [0.5, -0.5, 1.0, -1.0] } },
      },
    },
  ],
};

describe("residualQQSeries", () => {
  it("returns one series per solver that has residuals", () => {
    const s = residualQQSeries(report as any, "C1", ["a", "b"]);
    expect(s.map((x) => x.backend).sort()).toEqual(["a", "b"]);
  });

  it("length of points equals the number of residuals", () => {
    const s = residualQQSeries(report as any, "C1", ["a"]);
    expect(s[0].points).toHaveLength(residuals.length);
  });

  it("sample quantiles are monotone non-decreasing (sorted)", () => {
    const s = residualQQSeries(report as any, "C1", ["a"]);
    const pts = s[0].points;
    for (let i = 1; i < pts.length; i++) {
      expect(pts[i].sample).toBeGreaterThanOrEqual(pts[i - 1].sample);
    }
  });

  it("theoretical quantiles are monotone non-decreasing (sorted)", () => {
    const s = residualQQSeries(report as any, "C1", ["a"]);
    const pts = s[0].points;
    for (let i = 1; i < pts.length; i++) {
      expect(pts[i].theoretical).toBeGreaterThanOrEqual(pts[i - 1].theoretical);
    }
  });

  it("standardised sample mean ≈ 0 and sd ≈ 1", () => {
    const s = residualQQSeries(report as any, "C1", ["a"]);
    const pts = s[0].points;
    const vals = pts.map((p) => p.sample);
    const mean = vals.reduce((a, v) => a + v, 0) / vals.length;
    const sd = Math.sqrt(vals.reduce((a, v) => a + (v - mean) ** 2, 0) / vals.length);
    expect(mean).toBeCloseTo(0, 5);
    expect(sd).toBeCloseTo(1, 5);
  });

  it("falls back to ecdfResid when fit.resid is absent", () => {
    const r = {
      analyzed: [
        {
          id: "C2",
          profiles: {
            a: { ecdfResid: [{ x: 0.1, y: 0.1 }, { x: 0.2, y: 0.5 }, { x: 0.3, y: 0.9 }] },
          },
        },
      ],
    };
    const s = residualQQSeries(r as any, "C2", ["a"]);
    expect(s).toHaveLength(1);
    expect(s[0].points).toHaveLength(3);
  });

  it("omits backends with no residual data", () => {
    const s = residualQQSeries(report as any, "C1", ["a", "missing"]);
    expect(s.map((x) => x.backend)).not.toContain("missing");
  });

  it("uses the first analyzed case when caseId is not found", () => {
    const s = residualQQSeries(report as any, "UNKNOWN", ["a"]);
    expect(s).toHaveLength(1);
    expect(s[0].points).toHaveLength(residuals.length);
  });
});
