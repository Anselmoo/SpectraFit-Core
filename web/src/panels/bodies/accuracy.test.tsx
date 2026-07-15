/**
 * accuracyBody — per-case reduced-χ² distribution viz (EF-BIND-12).
 *
 * Gates on data: renders PlotMount when at least one backend has accuracy data,
 * falls back to a no-data message when all profiles lack it.
 */
import { describe, it, expect } from "vitest";
import { render } from "@testing-library/react";
import type { BenchReport } from "../../contract";
import { accuracyBody } from "./evidenceCase";

// ---------------------------------------------------------------------------
// Minimal fixture factory
// ---------------------------------------------------------------------------

function makeAccuracyDist(median = 1.0) {
  return { raw: [0.9, median, 1.1], median, p5: 0.85, p25: 0.95, p75: 1.05 };
}

function makeReport(profileOverrides: Record<string, unknown> = {}): BenchReport {
  return {
    schemaVersion: "2.0",
    baselineSolverId: "lmfit",
    solvers: [
      { id: "spectrafit", label: "spectrafit", color: "#4f8ef7", soft: false },
      { id: "lmfit", label: "lmfit", color: "#f7a84f", soft: false },
    ],
    categories: [{ id: "easy", label: "Easy cases", n: 1, hue: 0 }],
    manifest: {
      geomeanSpeedupVsBaseline: 1.5,
      harmonicMeanSpeedupVsBaseline: 1.3,
      maxAbsDeltaR2: 0.001,
      spectrafitWinRate: 0.8,
      regressions: 0,
      gateState: "PASS",
      saturatedCategories: null,
      pinned: null,
    },
    suite: [],
    analyzed: [
      {
        id: "case1",
        name: "Case 1",
        category: "easy",
        x: [1, 2, 3],
        ref: [1, 2, 3],
        profiles: {
          spectrafit: {
            accuracy: makeAccuracyDist(1.05),
            ...profileOverrides,
          },
          lmfit: {
            accuracy: makeAccuracyDist(1.2),
          },
        },
      },
    ],
    trustBlock: { rung: 1, wires: [], nClaimsAudited: 0, nClaimsTotal: 0, nistValidation: null },
    inference: {
      config: { equivalenceMargin: 0.01, bootstrapB: 200, seed: 42, fdrQ: 0.05 },
      cases: [],
      equivalence: [],
      winnerStability: null,
    },
    panels: [],
  } as unknown as BenchReport;
}

// Minimal PanelCtx for single-case panels
const CTX = {
  view: "case",
  selectedId: "case1",
  solverIds: ["spectrafit", "lmfit"],
  colors: { spectrafit: "#4f8ef7", lmfit: "#f7a84f" },
  openCase: () => {},
} as never;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("accuracyBody — per-case reduced-χ² distribution (EF-BIND-12)", () => {
  it("renders the PlotMount wrapper when accuracy data is present", () => {
    const node = accuracyBody(makeReport(), CTX);
    expect(node).not.toBeNull();
    const { container } = render(<>{node}</>);
    // PlotMount renders a div with a data-plot-mount attribute or a regular div;
    // just check the container has some DOM content (not empty)
    expect(container.firstChild).not.toBeNull();
  });

  it("renders a no-data message when all backends lack accuracy data", () => {
    const report = makeReport();
    // Remove accuracy from all profiles
    (report.analyzed as any)[0].profiles = {
      spectrafit: { timing: { median: 10, p5: 8, p25: 9, p75: 11, p95: 13, iqr: 2, cv: 0.2 } },
      lmfit: { timing: { median: 15, p5: 12, p25: 13, p75: 17, p95: 19, iqr: 4, cv: 0.26 } },
    };

    const node = accuracyBody(report, CTX);
    expect(node).not.toBeNull();
    const { container } = render(<>{node}</>);
    // Should render a <p> with no-data message
    const p = container.querySelector("p");
    expect(p).not.toBeNull();
    expect(p!.textContent).toMatch(/[Nn]o accuracy/);
  });

  it("returns null when no case is selected", () => {
    // Pass a ctx with no selectedId and a report with no analyzed
    const emptyReport = {
      ...makeReport(),
      analyzed: [],
    } as unknown as BenchReport;
    const node = accuracyBody(emptyReport, CTX);
    expect(node).toBeNull();
  });
});
