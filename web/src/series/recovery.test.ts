import { describe, it, expect } from "vitest";
import { recoveryRows } from "./recovery";

const f = {
  truth: [{ a: 5, c: 0, s: 1 }],
  guessParams: [{ a: 4, c: 0.2, s: 1.2 }],
  profiles: {
    lmfit: {
      fit: { params: [{ a: 5.01, c: 0.0, s: 1.0 }] },
      paramErr: [0.5],
    },
  },
};

describe("recoveryRows", () => {
  it("emits truth/guess/fit per param per backend", () => {
    const r = recoveryRows(f as any, ["lmfit"]);
    const aAmp = r.find((x) => x.param === "a0" && x.backend === "lmfit")!;
    expect(aAmp.truth).toBe(5);
    expect(aAmp.guess).toBe(4);
    expect(aAmp.fit).toBeCloseTo(5.01);
  });

  it("skips a backend with no fit params", () => {
    expect(recoveryRows(f as any, ["ghost"])).toEqual([]);
  });

  // EF-PLOTS-07: params of disparate magnitude must share one fair x-axis.
  // Each param is normalized to a signed deviation relative to its own scale
  // (truth maps to 0), so a 10³ amplitude and a 10⁻¹ width no longer collapse.
  it("normalizes each param to a relative deviation from truth (truth → 0, magnitude-fair)", () => {
    const r = recoveryRows(f as any, ["lmfit"]);
    const a = r.find((x) => x.param === "a0")!;
    expect(a.scale).toBe(5); // max(|truth=5|, |guess=4|)
    expect(a.guessDev).toBeCloseTo(-0.2); // (4 - 5) / 5
    expect(a.fitDev).toBeCloseTo(0.002); // (5.01 - 5) / 5

    // truth = 0 (center) must not divide-by-zero — scale falls back to |guess|
    const c = r.find((x) => x.param === "c0")!;
    expect(c.scale).toBe(0.2);
    expect(c.guessDev).toBeCloseTo(1); // (0.2 - 0) / 0.2
    expect(c.fitDev).toBe(0); // (0 - 0) / 0.2 — recovered

    // a backend's deviation scale is the SAME for a given param (truth/guess are
    // backend-independent) so cross-backend rows are comparable.
    expect(a.scale).toBe(r.find((x) => x.param === "a0" && x.backend === "lmfit")!.scale);
  });
});
