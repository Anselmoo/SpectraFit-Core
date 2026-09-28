import { describe, it, expect } from "vitest";
import { convSeries, thetaDistanceSeries } from "./convergence";
const f={profiles:{a:{conv:[10,5,2,1],historySource:"real"}, b:{conv:[9,3,1],historySource:"reconstructed"}}};
describe("convSeries",()=>{
  it("tags each backend line with its history mode",()=>{
    const s=convSeries(f as any,["a","b"]);
    expect(s.find(x=>x.backend==="a")!.mode).toBe("line");
    expect(s.find(x=>x.backend==="b")!.mode).toBe("endpoints");
    expect(s.find(x=>x.backend==="a")!.rows[1]).toEqual({iter:1,cost:5,backend:"a"});
  });
});

describe("thetaDistanceSeries (real convergence-to-truth)", () => {
  const synthetic = {
    profiles: {
      // Only the subject solver records a θ trajectory; found by data, not id.
      spectrafit: { thetaDistance: [1.2, 0.4, 0.05, 0.008], conv: [1, 0.5, 0.1] },
      lmfit: { thetaDistance: null, conv: [0.9, 0.3] },
    },
  };

  it("builds a decreasing distance series from the backend that has the field", () => {
    const out = thetaDistanceSeries(synthetic as any)!;
    expect(out).not.toBeNull();
    expect(out.backend).toBe("spectrafit");
    expect(out.rows).toHaveLength(4);
    expect(out.rows[0]).toEqual({ iter: 0, dist: 1.2 });
    expect(out.rows[3].dist).toBeCloseTo(0.008, 12);
    expect(out.rows[3].dist).toBeLessThan(out.rows[0].dist);
  });

  it("is subject-blind: finds the trajectory by data, never a hardcoded id", () => {
    // Same data under a different backend key still resolves.
    const renamed = { profiles: { mystery: { thetaDistance: [0.5, 0.1] } } };
    const out = thetaDistanceSeries(renamed as any)!;
    expect(out.backend).toBe("mystery");
    expect(out.rows).toHaveLength(2);
  });

  it("returns null when no backend carries a θ trajectory (non-synthetic case)", () => {
    expect(thetaDistanceSeries({ profiles: { a: { conv: [1, 0.5] } } } as any)).toBeNull();
    expect(thetaDistanceSeries({ profiles: {} } as any)).toBeNull();
    expect(thetaDistanceSeries({} as any)).toBeNull();
  });

  it("clamps to a tiny positive EPS so the log axis never sees ≤0", () => {
    const out = thetaDistanceSeries({ profiles: { sf: { thetaDistance: [0.1, 0] } } } as any)!;
    for (const r of out.rows) expect(r.dist).toBeGreaterThan(0);
  });
});
