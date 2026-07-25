import { describe, it, expect } from "vitest";
import { timingBoxes } from "./timing";

const f = {
  profiles: {
    lmfit: {
      timing: { p5: 1, p25: 2, median: 3, p75: 4, p95: 5 },
    },
  },
};

describe("timingBoxes", () => {
  it("projects percentiles per backend", () => {
    expect(timingBoxes(f as any, ["lmfit"])[0]).toEqual({
      backend: "lmfit",
      p5: 1,
      p25: 2,
      median: 3,
      p75: 4,
      p95: 5,
    });
  });

  it("skips backend without timing", () => {
    expect(timingBoxes(f as any, ["ghost"])).toEqual([]);
  });
});
