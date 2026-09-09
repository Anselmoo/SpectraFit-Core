import { describe, it, expect } from "vitest";
import { iterationsSeries } from "./iterations";

const report = {
  analyzed: [
    {
      id: "C1",
      category: "easy",
      profiles: {
        a: { summary: { nIter: 12 } },
        b: { summary: { nIter: 7 } },
        c: { summary: { nIter: 0 } },
      },
    },
  ],
};

describe("iterationsSeries", () => {
  it("returns one entry per backend with a valid nIter", () => {
    const s = iterationsSeries(report as any, "C1", ["a", "b", "c"]);
    expect(s.map((x) => x.backend).sort()).toEqual(["a", "b", "c"]);
  });

  it("nIter values are non-negative integers", () => {
    const s = iterationsSeries(report as any, "C1", ["a", "b", "c"]);
    for (const entry of s) {
      expect(entry.nIter).toBeGreaterThanOrEqual(0);
      expect(Number.isInteger(entry.nIter)).toBe(true);
    }
  });

  it("reads nIter correctly from summary", () => {
    const s = iterationsSeries(report as any, "C1", ["a"]);
    expect(s[0].nIter).toBe(12);
  });

  it("zero nIter is valid (solver converged in 0 extra iterations)", () => {
    const s = iterationsSeries(report as any, "C1", ["c"]);
    expect(s[0].nIter).toBe(0);
  });

  it("omits backends with no summary", () => {
    const s = iterationsSeries(report as any, "C1", ["a", "missing"]);
    expect(s.find((x) => x.backend === "missing")).toBeUndefined();
  });

  it("omits backends with non-finite or negative nIter", () => {
    const bad = {
      analyzed: [
        {
          id: "X",
          profiles: {
            a: { summary: { nIter: 5 } },
            b: { summary: { nIter: NaN } },
            c: { summary: { nIter: -3 } },
            d: { summary: { nIter: Infinity } },
          },
        },
      ],
    };
    const s = iterationsSeries(bad as any, "X", ["a", "b", "c", "d"]);
    expect(s.map((x) => x.backend)).toEqual(["a"]);
    expect(s[0].nIter).toBe(5);
  });

  it("falls back to first analyzed case when caseId not found", () => {
    const s = iterationsSeries(report as any, "UNKNOWN", ["a"]);
    expect(s).toHaveLength(1);
    expect(s[0].nIter).toBe(12);
  });

  it("returns empty for an empty analyzed array", () => {
    const s = iterationsSeries({ analyzed: [] } as any, "C1", ["a"]);
    expect(s).toEqual([]);
  });
});
