import { describe, it, expect } from "vitest";
import { pullSeries } from "./pulls";

// Honest-null fixture: σ-less backend emits coverage:null (EF-PY-06)
const fNull = { profiles:{ real:{uncertainty:{pulls:[0.1,-0.2,1.3],coverage:0.66,sigma:[0.2]}},
                            sigmaless:{uncertainty:{pulls:null,coverage:null,sigma:null}} } };

// Edge case: genuine 0% coverage (all |pulls| ≥ 1σ) is legitimate data, NOT absent
const fZeroCoverage = { profiles:{
  a:{uncertainty:{pulls:[1.5,-1.8,2.1,-1.2],coverage:0,sigma:[0.1,0.1,0.1,0.1]}}
} };

// Edge case: backend with no coverage field at all → coverage undefined, treated absent
const fUndefinedCoverage = { profiles:{
  a:{uncertainty:{pulls:[0.1],coverage:undefined,sigma:[0.2]}}
} };

describe("pullSeries",()=>{
  it("treats coverage===null as absent (honest null sentinel, EF-PY-06)",()=>{
    const s = pullSeries(fNull as any, ["real","sigmaless"]);
    expect(s.find(x=>x.backend==="real")!.absent).toBe(false);
    expect(s.find(x=>x.backend==="sigmaless")!.absent).toBe(true);
    expect(s.find(x=>x.backend==="real")!.coverage).toBeCloseTo(0.66);
  });

  it("treats coverage===0 with real pull data as NOT absent (genuine 0% coverage)",()=>{
    const s = pullSeries(fZeroCoverage as any, ["a"]);
    expect(s.find(x=>x.backend==="a")!.absent).toBe(false);
    expect(s.find(x=>x.backend==="a")!.coverage).toBe(0);
  });

  it("treats coverage===undefined as absent (missing field = no σ)",()=>{
    const s = pullSeries(fUndefinedCoverage as any, ["a"]);
    expect(s.find(x=>x.backend==="a")!.absent).toBe(true);
  });
});
