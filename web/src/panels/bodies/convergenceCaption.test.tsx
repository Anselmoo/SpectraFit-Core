/**
 * EF-PLOTS-08 — convergence caption must not hardcode backend ids.
 *
 * The caption for the "convergence" panel (registry.tsx) must derive the
 * reconstructed-backend list from the data (historySource === "reconstructed")
 * rather than literally naming "lmfit/jax". This test verifies that the caption
 * reflects the actual roster: if the reconstructed backends are X/Y, the caption
 * says so — not the old hardcoded string.
 */
import { describe, it, expect } from "vitest";
import { PANELS } from "../registry";
import type { BenchReport } from "../../contract";

function convergenceCaption(report: BenchReport): string {
  const rec = PANELS.find((p) => p.id === "convergence");
  if (!rec?.caption) return "";
  return typeof rec.caption === "function" ? rec.caption(report) : rec.caption;
}

/** Minimal report factory — supply analyzed cases with historySource set. */
function makeReport(analyzedProfiles: Array<Record<string, { historySource: string }>>): BenchReport {
  return {
    schemaVersion: "2.0",
    baselineSolverId: "lmfit",
    solvers: [],
    categories: [],
    manifest: {
      geomeanSpeedupVsBaseline: 1.0,
      harmonicMeanSpeedupVsBaseline: 1.0,
      maxAbsDeltaR2: 0.0,
      spectrafitWinRate: 1.0,
      regressions: 0,
      gateState: "PASS",
      saturatedCategories: null,
      pinned: null,
    },
    suite: [],
    analyzed: analyzedProfiles.map((profiles, i) => ({
      id: `case-${i}`,
      name: `Case ${i}`,
      category: "easy",
      x: [],
      ref: [],
      profiles,
    })),
    trustBlock: { rung: 1, wires: [], nClaimsAudited: 0, nClaimsTotal: 0, nistValidation: null },
    inference: {
      config: { equivalenceMargin: 0.001, bootstrapB: 200, seed: 1, fdrQ: 0.05 },
      cases: [],
      equivalence: [],
      winnerStability: null,
    },
    panels: [],
  } as unknown as BenchReport;
}

describe("EF-PLOTS-08 — convergence caption is data-derived, not hardcoded", () => {
  it("caption is produced by a function (data-derived), not a static string", () => {
    // The old caption was a static string. The new caption must be a function
    // so it can derive the reconstructed-backend list from the data.
    const rec = PANELS.find((p) => p.id === "convergence");
    expect(rec).toBeTruthy();
    expect(typeof rec!.caption).toBe("function");
  });

  it("caption names the reconstructed backends found in the data", () => {
    const report = makeReport([
      { lmfit: { historySource: "reconstructed" }, jax: { historySource: "reconstructed" }, sf: { historySource: "real" } },
    ]);
    const caption = convergenceCaption(report);
    // Both reconstructed backends must appear
    expect(caption).toMatch(/lmfit/);
    expect(caption).toMatch(/jax/);
    expect(caption).toMatch(/reconstructed/);
  });

  it("caption mentions only the actual reconstructed backend when roster changes", () => {
    // Roster changed: only 'proxy-backend' is reconstructed, lmfit is real.
    const report = makeReport([
      { "proxy-backend": { historySource: "reconstructed" }, real_sf: { historySource: "real" } },
    ]);
    const caption = convergenceCaption(report);
    expect(caption).toContain("proxy-backend");
    expect(caption).toMatch(/reconstructed/);
    // lmfit/jax must NOT appear — they are not in this roster
    expect(caption).not.toContain("lmfit");
    expect(caption).not.toContain("jax");
  });

  it("caption has no reconstructed-proxy suffix when all backends are measured/real", () => {
    const report = makeReport([
      { sf: { historySource: "real" }, other: { historySource: "real" } },
    ]);
    const caption = convergenceCaption(report);
    expect(caption).not.toContain("reconstructed");
    expect(caption).toContain("χ²");
  });

  it("caption works when analyzed is empty (no cases)", () => {
    const report = makeReport([]);
    const caption = convergenceCaption(report);
    // No crash, no reconstructed suffix
    expect(typeof caption).toBe("string");
    expect(caption.length).toBeGreaterThan(0);
  });
});
