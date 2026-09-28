import { describe, it, expect } from "vitest";
import { infoCriteriaRows } from "./infoCriteria";

const f = {
  profiles: {
    a: { summary: { dAIC: 0, dBIC: 0, mae: 0.01, aic: -100, bic: -90 } },
    b: { summary: { dAIC: 4.2, dBIC: 5.1, mae: 0.03, aic: -95.8, bic: -84.9 } },
    c: { summary: {} }, // no info-criteria → skipped
    d: {}, // no summary → skipped
  },
};

describe("infoCriteriaRows", () => {
  it("returns one row per backend that reports info criteria", () => {
    const rows = infoCriteriaRows(f as any, ["a", "b", "c", "d"]);
    expect(rows.map((r) => r.backend)).toEqual(["a", "b"]);
  });

  it("carries dAIC, dBIC, mae per backend", () => {
    const rows = infoCriteriaRows(f as any, ["a", "b"]);
    const b = rows.find((r) => r.backend === "b")!;
    expect(b.dAIC).toBe(4.2);
    expect(b.dBIC).toBe(5.1);
    expect(b.mae).toBe(0.03);
  });

  it("flags the preferred backend (lowest dAIC) as best", () => {
    const rows = infoCriteriaRows(f as any, ["a", "b"]);
    expect(rows.find((r) => r.backend === "a")!.best).toBe(true);
    expect(rows.find((r) => r.backend === "b")!.best).toBe(false);
  });

  it("skips a backend whose summary lacks dAIC (no fabricated 0)", () => {
    const rows = infoCriteriaRows(f as any, ["a", "c"]);
    expect(rows.map((r) => r.backend)).toEqual(["a"]);
  });

  it("empty roster → empty rows", () => {
    expect(infoCriteriaRows(f as any, [])).toEqual([]);
  });
});
