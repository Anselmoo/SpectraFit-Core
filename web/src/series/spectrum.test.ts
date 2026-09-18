import { describe, it, expect } from "vitest";
import { spectrumSeries, metricRows, residualRows } from "./spectrum";

const featured = {
  id: "EZ-001", x: [0, 1, 2], ref: [1, 2, 1], guess: [0.8, 1.8, 0.9],
  profiles: {
    lmfit: { fit: { curve: [1.0, 2.0, 1.0], resid: [0, 0, 0] }, summary: { r2: 0.99, redChi2: 1.1, rmse: 0.01, speedup: 1, nIter: 5 } },
    spectrafit: { fit: { curve: [1.01, 1.99, 1.0], resid: [0.01, -0.01, 0] }, summary: { r2: 0.999, redChi2: 1.0, rmse: 0.005, speedup: 12, nIter: 4 } },
  },
};

describe("spectrumSeries", () => {
  it("emits ref markers, a guess line, and one fit line per backend", () => {
    const s = spectrumSeries(featured as any, ["lmfit", "spectrafit"]);
    expect(s.ref).toEqual([{ x: 0, y: 1 }, { x: 1, y: 2 }, { x: 2, y: 1 }]);
    expect(s.guess[1]).toEqual({ x: 1, y: 1.8 });
    expect(s.fits.map((f) => f.backend)).toEqual(["lmfit", "spectrafit"]);
    expect(s.fits[1].rows[0]).toEqual({ x: 0, y: 1.01, backend: "spectrafit" });
  });
  it("skips a backend with no profile", () => {
    const s = spectrumSeries(featured as any, ["lmfit", "ghost"]);
    expect(s.fits.map((f) => f.backend)).toEqual(["lmfit"]);
  });
});

describe("residualRows", () => {
  // A backend whose stored resid uses the MIRRORED convention (fit − obs) must
  // still render with the same sign as one using obs − fit, because residualRows
  // recomputes ref − fit.curve and ignores the stored sign entirely.
  const mirrored = {
    id: "EZ-001",
    x: [0, 1, 2],
    ref: [1, 2, 1],
    guess: [0.8, 1.8, 0.9],
    profiles: {
      // obs − fit convention stored
      goodSign: { fit: { curve: [1.1, 1.8, 0.9], resid: [-0.1, 0.2, 0.1] } },
      // fit − obs convention stored (mirror): same curve, opposite stored sign
      mirrorSign: { fit: { curve: [1.1, 1.8, 0.9], resid: [0.1, -0.2, -0.1] } },
    },
  };

  it("normalizes every backend to obs − fit by recomputing from ref + curve", () => {
    const rows = residualRows(mirrored as any, ["goodSign", "mirrorSign"]);
    const good = rows.filter((r) => r.backend === "goodSign");
    const mirror = rows.filter((r) => r.backend === "mirrorSign");
    // Both backends share the same curve, so after recompute their residuals are identical.
    expect(good.map((r) => r.y)).toEqual(mirror.map((r) => r.y));
    // And they all follow obs − fit: ref[1]=2, curve[1]=1.8 → +0.2.
    expect(good[1].y).toBeCloseTo(0.2, 12);
  });

  it("makes all backends share residual sign at every point on a clean case", () => {
    const rows = residualRows(mirrored as any, ["goodSign", "mirrorSign"]);
    for (let i = 0; i < mirrored.x.length; i++) {
      const atI = rows.filter((r) => r.x === mirrored.x[i]).map((r) => Math.sign(r.y));
      const signs = new Set(atI.filter((s) => s !== 0));
      expect(signs.size).toBeLessThanOrEqual(1);
    }
  });

  it("falls back to stored resid only when the fit curve is absent", () => {
    const noCurve = {
      x: [0, 1],
      ref: [1, 1],
      profiles: { b: { fit: { resid: [0.5, -0.5] } } },
    };
    const rows = residualRows(noCurve as any, ["b"]);
    expect(rows.map((r) => r.y)).toEqual([0.5, -0.5]);
  });

  it("skips a backend with neither curve nor stored resid", () => {
    const empty = { x: [0], ref: [1], profiles: { b: { fit: {} } } };
    expect(residualRows(empty as any, ["b"])).toEqual([]);
  });
});

describe("metricRows", () => {
  it("projects per-backend summary metrics", () => {
    const rows = metricRows(featured as any, ["lmfit", "spectrafit"]);
    const sf = rows.find((r) => r.backend === "spectrafit")!;
    expect(sf.r2).toBe(0.999); expect(sf.speedup).toBe(12); expect(sf.rmse).toBe(0.005);
  });
});
