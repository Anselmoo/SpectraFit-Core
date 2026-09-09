import { describe, it, expect } from "vitest";
import { scalingLines } from "./scaling";

const f = { profiles: { lmfit: { scaling: [{ x: 128, y: 1.2 }, { x: 512, y: 5.1 }] } } };

describe("scalingLines", () => {
  it("maps scaling points to {n,ms} rows", () => {
    const s = scalingLines(f as any, ["lmfit"])[0];
    expect(s.rows[1]).toEqual({ n: 512, ms: 5.1, backend: "lmfit" });
  });

  it("skips backend without scaling", () => {
    expect(scalingLines(f as any, ["ghost"])).toEqual([]);
  });
});
