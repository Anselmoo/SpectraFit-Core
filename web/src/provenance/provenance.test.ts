import { describe, it, expect } from "vitest";
import { Provenance, provStyle, historyMode, titleGuard, PROV_ORDER } from "./index";

describe("provenance materials (certainty gradient)", () => {
  it("maps each provenance to a distinct token-backed class", () => {
    const classes = PROV_ORDER.map(p => provStyle(p).className);
    expect(new Set(classes).size).toBe(PROV_ORDER.length); // all distinct
  });
  it("uses CSS variables, never hardcoded hex", () => {
    for (const p of PROV_ORDER) {
      expect(provStyle(p).color).toMatch(/var\(--prov-/);
    }
  });
  it("a fixture pair differing only in provenance renders differently", () => {
    expect(provStyle("measured")).not.toEqual(provStyle("reconstructed"));
  });
});

describe("convergence history mode", () => {
  it("real history is a solid line", () => {
    expect(historyMode("real")).toBe("line");
  });
  it("reconstructed history is endpoint-markers (never a solid line that implies it was measured)", () => {
    expect(historyMode("reconstructed")).toBe("endpoints");
  });
});

describe("data-existence title guard", () => {
  it("forbids a real-measurement title on synthetic data", () => {
    expect(() => titleGuard("2-D RIXS map", "synthetic")).toThrowError(/synthetic/i);
    expect(() => titleGuard("Experimental spectrum", "synthetic")).toThrowError(/synthetic/i);
  });
  it("allows a synthetic-recovery title on synthetic data", () => {
    expect(titleGuard("Synthetic recovery — 2-D", "synthetic")).toMatch(/recovery/i);
  });
  it("allows any title on measured data", () => {
    expect(titleGuard("2-D RIXS map", "measured")).toBe("2-D RIXS map");
  });
});
