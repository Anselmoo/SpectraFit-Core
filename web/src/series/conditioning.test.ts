import { describe, it, expect } from "vitest";
import { kappaRows, topCouplings } from "./conditioning";

const f = {
  profiles: {
    a: { jacobianConditionNumber: 1e7 },
    b: { jacobianConditionNumber: 50 },
    c: { jacobianConditionNumber: null },
  },
  corr: [[1, 0.9, 0.1], [0.9, 1, -0.5], [0.1, -0.5, 1]],
  paramNames: ["a0", "c0", "s0"],
};

describe("kappaRows", () => {
  it("flags ill-posed and absent", () => {
    const r = kappaRows(f as any, ["a", "b", "c"]);
    expect(r.find((x) => x.backend === "a")!.illPosed).toBe(true);
    expect(r.find((x) => x.backend === "b")!.illPosed).toBe(false);
    expect(r.find((x) => x.backend === "c")!.absent).toBe(true);
  });
});

describe("topCouplings", () => {
  it("returns top-|r| pairs", () => {
    const c = topCouplings(f as any, 2);
    expect(c[0]).toEqual({ pair: "a0·c0", r: 0.9 });
    expect(c[1].pair).toBe("c0·s0");
  });
});
