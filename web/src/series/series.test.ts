import { describe, it, expect } from "vitest";
import { tickLabels, ciRows } from "./index";

describe("tick formatter — no adjacent-equal labels", () => {
  it("disambiguates near-equal linear ticks instead of collapsing them", () => {
    const ticks = [0.05638, 0.05639, 0.05640];
    const labels = tickLabels(ticks, "linear");
    expect(new Set(labels).size).toBe(labels.length); // all distinct
  });
  it("formats log ticks without two identical adjacent labels", () => {
    const ticks = [1, 10, 100, 1000, 10000];
    const labels = tickLabels(ticks, "log");
    expect(new Set(labels).size).toBe(labels.length);
  });
  it("keeps short labels for clean values", () => {
    expect(tickLabels([0, 1, 2], "linear")).toEqual(["0", "1", "2"]);
  });
});

describe("ciRows — typed rows from inference cases", () => {
  it("maps a CaseInference list to {caseId, lo, point, hi} rows", () => {
    const cases = [
      { caseId: "EZ-001", speedupCi: { lo: 8, point: 10, hi: 12 }, deltaR2Ci: { lo: -1e-4, point: 0, hi: 1e-4 } },
    ];
    const rows = ciRows(cases as any, "speedupCi");
    expect(rows).toEqual([{ caseId: "EZ-001", lo: 8, point: 10, hi: 12 }]);
  });
  it("is pure — returns a new array, no DOM/color", () => {
    const rows = ciRows([] as any, "speedupCi");
    expect(rows).toEqual([]);
  });
  it("skips cases where the requested field is missing — no throw", () => {
    const cases = [
      { caseId: "EZ-001", speedupCi: { lo: 8, point: 10, hi: 12 } },
      { caseId: "EZ-002" /* no speedupCi */ },
      { caseId: "EZ-003", speedupCi: { lo: 1, point: 2, hi: 3 } },
    ];
    expect(() => ciRows(cases as any, "speedupCi")).not.toThrow();
    const rows = ciRows(cases as any, "speedupCi");
    expect(rows).toEqual([
      { caseId: "EZ-001", lo: 8, point: 10, hi: 12 },
      { caseId: "EZ-003", lo: 1, point: 2, hi: 3 },
    ]);
  });
  it("returns [] when every case is missing the field", () => {
    const cases = [{ caseId: "EZ-001" }, { caseId: "EZ-002" }];
    expect(ciRows(cases as any, "speedupCi")).toEqual([]);
  });
});
