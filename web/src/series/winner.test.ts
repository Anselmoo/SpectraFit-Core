import { describe, it, expect } from "vitest";
import { winnerBars } from "./winner";

describe("winnerBars", () => {
  it("sorts desc and flags a robust winner", () => {
    const s = winnerBars({ a: 0.1, b: 0.88, c: 0.02 });
    expect(s.bars[0]).toEqual({ backend: "b", fraction: 0.88 });
    expect(s.noRobustWinner).toBe(false);
  });

  it("flags no robust winner when max < 0.6", () => {
    expect(winnerBars({ a: 0.5, b: 0.5 }).noRobustWinner).toBe(true);
  });
});
