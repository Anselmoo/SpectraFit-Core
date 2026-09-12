import { describe, it, expect } from "vitest";
import { warmupLines } from "./warmup";
const f={profiles:{jax:{warmup:{coldMs:100,hotMs:2,curve:[{x:1,y:100},{x:2,y:51}]}}}};
describe("warmupLines",()=>{
  it("maps curve to {n,perRun} rows",()=>{
    const w=warmupLines(f as any,["jax"])[0];
    expect(w.coldMs).toBe(100); expect(w.rows[1]).toEqual({n:2,perRun:51,backend:"jax"});
  });
  it("skips backend without warmup",()=>{ expect(warmupLines(f as any,["ghost"])).toEqual([]); });
});
