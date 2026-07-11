import { describe, it, expect } from "vitest";
import { saturationGrid } from "./saturation";

const suite = [
  { id: "EZ-1", category: "easy", m: { lmfit: { r2: 0.999 }, spectrafit: { r2: 0.9995 } } },
  { id: "EZ-2", category: "easy", m: { lmfit: { r2: 0.998 }, spectrafit: { r2: 0.9985 } } },
  { id: "OF-1", category: "optfn", m: { lmfit: { r2: 0.40 }, spectrafit: { r2: 0.35 } } },
];

describe("saturationGrid", () => {
  it("computes mean r2 per (category, backend)", () => {
    const rows = saturationGrid(suite as any);
    const easyLmfit = rows.find((r) => r.category === "easy" && r.backend === "lmfit");
    expect(easyLmfit?.r2).toBeCloseTo((0.999 + 0.998) / 2, 6);
    const ofSf = rows.find((r) => r.category === "optfn" && r.backend === "spectrafit");
    expect(ofSf?.r2).toBeCloseTo(0.35, 6);
  });
  it("covers every category × backend present", () => {
    const rows = saturationGrid(suite as any);
    expect(new Set(rows.map((r) => r.category))).toEqual(new Set(["easy", "optfn"]));
    expect(new Set(rows.map((r) => r.backend))).toEqual(new Set(["lmfit", "spectrafit"]));
  });
  it("tags cells with r²<0.9 as failed=true and r²≥0.9 as failed=false", () => {
    const rows = saturationGrid(suite as any);
    // easy/lmfit mean ≈0.9985 → not failed
    const easyLmfit = rows.find((r) => r.category === "easy" && r.backend === "lmfit");
    expect(easyLmfit?.failed).toBe(false);
    // optfn/lmfit r²=0.40 → failed
    const ofLmfit = rows.find((r) => r.category === "optfn" && r.backend === "lmfit");
    expect(ofLmfit?.failed).toBe(true);
    // optfn/spectrafit r²=0.35 → failed
    const ofSf = rows.find((r) => r.category === "optfn" && r.backend === "spectrafit");
    expect(ofSf?.failed).toBe(true);
  });
  it("a cell with r²=0.9 exactly is NOT marked failed (the floor is an exclusive lower bound)", () => {
    const exactFloor = [
      { id: "X-1", category: "cat", m: { lmfit: { r2: 0.9 } } },
    ];
    const rows = saturationGrid(exactFloor as any);
    expect(rows[0].failed).toBe(false);
  });
});
