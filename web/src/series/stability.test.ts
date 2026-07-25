import { describe, it, expect } from "vitest";
import { stabilityBand } from "./stability";

const f = {
  profiles: {
    lmfit: {
      stability: {
        r2: [
          { n: 5, mean: 0.99, sd: 0.01 },
          { n: 20, mean: 0.995, sd: 0.002 },
        ],
      },
    },
  },
};

describe("stabilityBand", () => {
  it("builds mean±sd band rows", () => {
    const s = stabilityBand(f as any, ["lmfit"], "r2")[0];
    expect(s.rows[0]).toEqual({
      n: 5,
      mean: 0.99,
      lo: 0.98,
      hi: 1.0,
      backend: "lmfit",
    });
  });

  it("skips backend without the metric", () => {
    expect(stabilityBand(f as any, ["ghost"], "r2")).toEqual([]);
  });
});
