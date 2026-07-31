import { describe, it, expect } from "vitest";
import { peakRows } from "./peaks";
const f = { x:[0,1,2], peaks:[{label:"p1", y:[0.1,0.9,0.1]},{label:"p2", y:[0,0.2,0]}] };
describe("peakRows", () => {
  it("flattens peaks to {x,y,label} rows", () => {
    const r = peakRows(f as any);
    expect(r[1]).toEqual({ x:1, y:0.9, label:"p1" });
    expect(new Set(r.map(p=>p.label))).toEqual(new Set(["p1","p2"]));
  });
  it("empty-safe when no peaks", () => { expect(peakRows({x:[0],peaks:[]} as any)).toEqual([]); });
});
