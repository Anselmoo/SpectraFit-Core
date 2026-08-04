import { describe, it, expect, vi } from "vitest";
import {
  loadReport, SUPPORTED_SCHEMA, assertSupported,
  solversOf, analyzedById, profOf, defaultCaseId,
} from "./index";

const fixture = (over: any = {}) => ({
  schemaVersion: "1.4",
  solvers: [
    { id: "lmfit", label: "lmfit", color: "#888", soft: "#444" },
    { id: "spectrafit", label: "spectrafit", color: "#0cf", soft: "#066" },
  ],
  analyzed: [{ id: "EZ-001", profiles: { lmfit: { x: 1 }, spectrafit: { x: 2 } } }],
  suite: [], baselineSolverId: "lmfit",
  ...over,
});

describe("schema-version gate", () => {
  it("accepts a supported version", () => {
    expect(() => assertSupported(fixture())).not.toThrow();
  });
  it("accepts the current 1.6 schema", () => {
    expect(() => assertSupported(fixture({ schemaVersion: "1.6" }))).not.toThrow();
  });
  it("throws an explicit error on an unsupported version (never blank)", () => {
    expect(() => assertSupported(fixture({ schemaVersion: "0.9" })))
      .toThrowError(/unsupported schema/i);
  });
});

describe("subject-blind enumeration", () => {
  it("solversOf returns the ids from the data, in order", () => {
    expect(solversOf(fixture() as any)).toEqual(["lmfit", "spectrafit"]);
  });
  it("analyzedById returns undefined for a missing id (NO PRIMARY fallback)", () => {
    expect(analyzedById(fixture() as any, "NOPE")).toBeUndefined();
  });
  it("analyzedById finds an existing case", () => {
    expect(analyzedById(fixture() as any, "EZ-001")?.id).toBe("EZ-001");
  });
  it("profOf returns the per-backend profile or undefined", () => {
    const f = analyzedById(fixture() as any, "EZ-001")!;
    expect(profOf(f, "spectrafit")).toEqual({ x: 2 });
    expect(profOf(f, "ghost")).toBeUndefined();
  });
});

describe("defaultCaseId", () => {
  const sm = (r2: number) => ({ speedup: 1, r2, redChi2: 1, medMs: 1, paramErr: 0, success: true });
  const report = {
    schemaVersion: "1.4",
    solvers: [{ id: "a" }, { id: "b" }],
    analyzed: [{ id: "EZ-001" }, { id: "OF-010" }, { id: "CX-001" }],
    suite: [
      // saturated easy case — backends identical
      { id: "EZ-001", m: { a: sm(0.999), b: sm(0.999) } },
      // discriminating case — large r² spread
      { id: "OF-010", m: { a: sm(0.82), b: sm(0.35) } },
      // moderate spread
      { id: "CX-001", m: { a: sm(0.99), b: sm(0.97) } },
    ],
  };

  it("picks the case with the largest r² spread across backends", () => {
    expect(defaultCaseId(report as any)).toBe("OF-010");
  });

  it("only considers cases that exist in analyzed", () => {
    const r = {
      ...report,
      analyzed: [{ id: "EZ-001" }, { id: "CX-001" }], // OF-010 NOT analyzed
      suite: report.suite,
    };
    // OF-010 has the biggest spread but isn't analyzable → next best is CX-001.
    expect(defaultCaseId(r as any)).toBe("CX-001");
  });

  it("falls back to analyzed[0] when no suite r² spread is usable", () => {
    const r = { schemaVersion: "1.4", solvers: [{ id: "a" }], analyzed: [{ id: "EZ-001" }], suite: [] };
    expect(defaultCaseId(r as any)).toBe("EZ-001");
  });
});

describe("loadReport", () => {
  it("throws on non-ok fetch", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false, status: 503 })));
    await expect(loadReport()).rejects.toThrow(/503/);
  });
  it("gates an unsupported payload from a 200 response", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => fixture({ schemaVersion: "0.9" }) })));
    await expect(loadReport()).rejects.toThrow(/unsupported schema/i);
  });
});
