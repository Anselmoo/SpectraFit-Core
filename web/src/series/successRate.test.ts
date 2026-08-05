import { describe, it, expect } from "vitest";
import { successRateSeries } from "./successRate";

const report = {
  suite: [
    { id: "C1", category: "easy", m: { a: { success: true }, b: { success: true } } },
    { id: "C2", category: "easy", m: { a: { success: false }, b: { success: true } } },
    { id: "C3", category: "hard", m: { a: { success: true }, b: { success: false } } },
  ],
};

describe("successRateSeries", () => {
  it("computes successFraction = mean(success) per (category, backend)", () => {
    const rows = successRateSeries(report as any, ["a", "b"]);
    const easyA = rows.find((r) => r.category === "easy" && r.backend === "a")!;
    expect(easyA.successFraction).toBeCloseTo(0.5, 12); // true,false → 0.5
    const easyB = rows.find((r) => r.category === "easy" && r.backend === "b")!;
    expect(easyB.successFraction).toBe(1); // true,true → 1
    const hardA = rows.find((r) => r.category === "hard" && r.backend === "a")!;
    expect(hardA.successFraction).toBe(1);
  });

  it("all fractions lie within [0,1]", () => {
    const rows = successRateSeries(report as any, ["a", "b"]);
    for (const r of rows) {
      expect(r.successFraction).toBeGreaterThanOrEqual(0);
      expect(r.successFraction).toBeLessThanOrEqual(1);
    }
  });

  it("categories are the distinct suite[].category values", () => {
    const rows = successRateSeries(report as any, ["a", "b"]);
    const cats = [...new Set(rows.map((r) => r.category))].sort();
    expect(cats).toEqual(["easy", "hard"]);
  });

  it("emits one row per (category × backend)", () => {
    const rows = successRateSeries(report as any, ["a", "b"]);
    expect(rows).toHaveLength(4); // 2 categories × 2 backends
  });

  it("omits a (category,backend) pair with no measured cases", () => {
    const sparse = { suite: [{ id: "C1", category: "easy", m: { a: { success: true } } }] };
    const rows = successRateSeries(sparse as any, ["a", "b"]);
    expect(rows.some((r) => r.backend === "b")).toBe(false);
  });
});
