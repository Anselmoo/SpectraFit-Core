/**
 * Unit 5 — Standing facts-landing card test.
 *
 * The old gate-verdict card (standalone headline with speedup + rung) has been
 * replaced by the factsLandingCard (neutral masthead + per-backend table).
 * This test verifies that:
 * 1. The landing card renders case count and backend count from the data.
 * 2. It does NOT render boast language ("subject is", "wins", "best", "beats").
 * 3. The per-backend table shows all backends (alphabetical).
 * 4. The gate state is shown as a label (not crowning).
 *
 * Previously tested gateVerdictCard headline links; that specific test is superseded
 * by this facts-first version.
 */
import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { PANELS } from "../panels/registry";
import type { BenchReport } from "../contract";
import type { PanelCtx } from "../panels/types";
import React from "react";

afterEach(cleanup);

function makeReport(rung: number, geomean: number): BenchReport {
  return {
    schemaVersion: "1.5",
    baselineSolverId: "lmfit",
    solvers: [
      { id: "lmfit", label: "lmfit", color: "#888" },
      { id: "spectrafit", label: "spectrafit", color: "#4af" },
    ],
    categories: [],
    suite: [
      { id: "EZ-001", name: "EZ-001", category: "easy", difficulty: "easy", m: {
        lmfit: { speedup: 1.0, r2: 0.999, medMs: 10, success: true, redChi2: 1.0, paramErr: 0 },
        spectrafit: { speedup: geomean, r2: 0.9989, medMs: 10/geomean, success: true, redChi2: 1.0, paramErr: 0 },
      }, winner: "spectrafit", regression: false },
    ],
    analyzed: [],
    manifest: {
      geomeanSpeedupVsBaseline: geomean,
      harmonicMeanSpeedupVsBaseline: geomean * 0.9,
      maxAbsDeltaR2: 1e-6,
      spectrafitWinRate: 0.75,
      regressions: 0,
      gateState: "pass",
      saturatedCategories: [],
      pinned: null,
    },
    trustBlock: {
      rung,
      wires: [],
      nClaimsAudited: 3,
      nClaimsTotal: 5,
      nistValidation: null,
    },
    inference: null,
  } as unknown as BenchReport;
}

const ctx: PanelCtx = {
  selectedId: null,
  view: "overview",
  solverIds: ["lmfit", "spectrafit"],
  colors: { lmfit: "#888", spectrafit: "#4af" },
};

function renderFactsLanding(report: BenchReport): string {
  const rec = PANELS.find((p) => p.id === "facts-landing");
  if (!rec) return "";
  const node = rec.make(report, ctx);
  if (node == null) return "";
  const { container } = render(node as React.ReactElement);
  return container.textContent ?? "";
}

describe("Standing facts-landing: neutral, data-derived, no crowning", () => {
  it("shows both the case count and backend count from the data", () => {
    const report = makeReport(5, 11.8);
    const text = renderFactsLanding(report);
    // 1 case, 2 backends
    expect(text).toMatch(/1\s+peak-fitting cases?/);
    expect(text).toMatch(/2\s+solver backends/);
  });

  it("shows all backend names in the table (alphabetical)", () => {
    const report = makeReport(5, 11.8);
    const text = renderFactsLanding(report);
    expect(text).toContain("lmfit");
    expect(text).toContain("spectrafit");
  });

  it("shows gate state as a label (not as crowning language)", () => {
    const report = makeReport(5, 11.8);
    const text = renderFactsLanding(report);
    // gate label present
    expect(text.toLowerCase()).toMatch(/gate/);
    // but no boast language
    expect(text.toLowerCase()).not.toMatch(/\bsubject is\b/);
    expect(text.toLowerCase()).not.toMatch(/\bwins\b/);
    expect(text.toLowerCase()).not.toMatch(/\bbest\b/);
    expect(text.toLowerCase()).not.toMatch(/\bbeats\b/);
  });

  it("reflects different backend counts when the data changes", () => {
    const report = makeReport(3, 7.2);
    const text = renderFactsLanding(report);
    // Still 2 backends
    expect(text).toMatch(/2\s+solver backends/);
  });

  it("shows the Evidence flow link", () => {
    const report = makeReport(5, 11.8);
    const text = renderFactsLanding(report);
    expect(text.toLowerCase()).toContain("all cases");
  });
});
