/**
 * Saturation-panel chip row — EF-BIND-11.
 *
 * The saturation body must render a chip for each id in
 * manifest.saturatedCategories, using the category's human label.
 * When the list is absent or empty, no chip element may render.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import type { BenchReport } from "../../contract";
import { saturationBody } from "./evidenceOverview";

// ---------------------------------------------------------------------------
// Minimal fixture factory
// ---------------------------------------------------------------------------

function makeReport(overrides: Partial<BenchReport> = {}): BenchReport {
  return {
    schemaVersion: "2.0",
    baselineSolverId: "lmfit",
    solvers: [
      { id: "spectrafit", label: "spectrafit", color: "#4f8ef7", soft: false },
      { id: "lmfit", label: "lmfit", color: "#f7a84f", soft: false },
    ],
    categories: [
      { id: "easy", label: "Easy cases", n: 3, hue: 0 },
      { id: "reality", label: "Reality checks", n: 2, hue: 120 },
      { id: "complex", label: "Complex peaks", n: 4, hue: 240 },
    ],
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
    suite: [
      { id: "c1", name: "c1", category: "easy", difficulty: "easy", m: {
        spectrafit: { speedup: 1.5, r2: 0.99, redChi2: 1.0, medMs: 10, paramErr: 0, success: true },
        lmfit: { speedup: 1.0, r2: 0.99, redChi2: 1.0, medMs: 15, paramErr: 0, success: true },
      }, winner: "spectrafit", regression: false },
    ],
    ...overrides,
  } as unknown as BenchReport;
}

// A minimal PanelCtx (only fields saturationBody actually uses)
const CTX = { view: "overview", solverIds: ["spectrafit", "lmfit"], colors: {}, openCase: () => {} } as never;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("saturationBody — saturated-category chips (EF-BIND-11)", () => {
  it("renders chips for each id in manifest.saturatedCategories", () => {
    const report = makeReport({
      manifest: {
        geomeanSpeedupVsBaseline: 1.5,
        harmonicMeanSpeedupVsBaseline: 1.3,
        maxAbsDeltaR2: 0.001,
        spectrafitWinRate: 0.8,
        regressions: 0,
        gateState: "PASS",
        saturatedCategories: ["easy", "reality"],
        pinned: null,
      },
    } as Partial<BenchReport>);

    const node = saturationBody(report, CTX);
    const { container } = render(<>{node}</>);

    // Chips must show the human label from categories[], not the raw id.
    expect(screen.getByText("Easy cases")).toBeTruthy();
    expect(screen.getByText("Reality checks")).toBeTruthy();

    // aria-label on the container row
    const row = container.querySelector('[aria-label="saturated categories"]');
    expect(row).not.toBeNull();

    // Two chip spans inside the row
    const chips = row!.querySelectorAll('[aria-label="saturated category"]');
    expect(chips).toHaveLength(2);
  });

  it("falls back to the raw id when the category label is absent", () => {
    const report = makeReport({
      manifest: {
        geomeanSpeedupVsBaseline: 1.5,
        harmonicMeanSpeedupVsBaseline: 1.3,
        maxAbsDeltaR2: 0.001,
        spectrafitWinRate: 0.8,
        regressions: 0,
        gateState: "PASS",
        saturatedCategories: ["unknown_cat"],
        pinned: null,
      },
    } as Partial<BenchReport>);

    const node = saturationBody(report, CTX);
    render(<>{node}</>);
    expect(screen.getByText("unknown_cat")).toBeTruthy();
  });

  it("renders no chip row when saturatedCategories is null", () => {
    const report = makeReport(); // default: saturatedCategories: null
    const node = saturationBody(report, CTX);
    const { container } = render(<>{node}</>);
    expect(container.querySelector('[aria-label="saturated categories"]')).toBeNull();
    expect(container.querySelector('[aria-label="saturated category"]')).toBeNull();
  });

  it("renders no chip row when saturatedCategories is an empty array", () => {
    const report = makeReport({
      manifest: {
        geomeanSpeedupVsBaseline: 1.5,
        harmonicMeanSpeedupVsBaseline: 1.3,
        maxAbsDeltaR2: 0.001,
        spectrafitWinRate: 0.8,
        regressions: 0,
        gateState: "PASS",
        saturatedCategories: [],
        pinned: null,
      },
    } as Partial<BenchReport>);

    const node = saturationBody(report, CTX);
    const { container } = render(<>{node}</>);
    expect(container.querySelector('[aria-label="saturated categories"]')).toBeNull();
    expect(container.querySelector('[aria-label="saturated category"]')).toBeNull();
  });

  it("renders no chip row when manifest is absent", () => {
    const report = makeReport({ manifest: undefined } as Partial<BenchReport>);
    const node = saturationBody(report, CTX);
    const { container } = render(<>{node}</>);
    expect(container.querySelector('[aria-label="saturated categories"]')).toBeNull();
  });
});
