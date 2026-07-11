/**
 * Wave B1 — code-provenance + winner-why panel tests.
 *
 * TDD red-first: verifies the provenanceBody function renders winnerReason,
 * modelSourceFile, modelFormula, and per-backend convergenceEfficiency /
 * illConditioned when present — and renders nothing when all fields are absent.
 */
import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { provenanceBody } from "./codeProvenance";
import type { BenchReport } from "../../contract";
import type { PanelCtx } from "../types";

afterEach(cleanup);

// ---------------------------------------------------------------------------
// Minimal fixture factory
// ---------------------------------------------------------------------------

function makeReport(overrides: {
  modelSourceFile?: string | null;
  modelFormula?: string | null;
  winnerReason?: string | null;
  convergenceEfficiency?: number | null;
  illConditioned?: boolean | null;
} = {}): BenchReport {
  const { modelSourceFile, modelFormula, winnerReason, convergenceEfficiency, illConditioned } = overrides;
  return {
    schemaVersion: "1.5",
    baselineSolverId: "lmfit",
    solvers: [
      { id: "lmfit", label: "lmfit", color: "#888" },
      { id: "spectrafit", label: "spectrafit", color: "#4af" },
    ],
    categories: [],
    suite: [
      {
        id: "EZ-001",
        name: "EZ-001 gaussian",
        category: "easy",
        difficulty: 1,
        winner: "spectrafit",
        regression: false,
        winnerReason: winnerReason ?? null,
        m: {
          lmfit: {
            speedup: 1.0, r2: 0.999, redChi2: 1.0, medMs: 0.30, paramErr: 0.001, success: true,
            convergenceEfficiency: convergenceEfficiency ?? null,
            illConditioned: illConditioned ?? null,
          },
          spectrafit: {
            speedup: 2.0, r2: 0.999, redChi2: 1.0, medMs: 0.15, paramErr: 0.001, success: true,
            convergenceEfficiency: convergenceEfficiency ?? null,
            illConditioned: illConditioned ?? null,
          },
        },
      },
    ],
    analyzed: [
      {
        id: "EZ-001",
        name: "EZ-001 gaussian",
        category: "easy",
        x: [],
        ref: [],
        profiles: {},
        modelSourceFile: modelSourceFile ?? null,
        modelFormula: modelFormula ?? null,
      },
    ],
    manifest: {
      geomeanSpeedupVsBaseline: 2.0,
      maxAbsDeltaR2: 1e-6,
      spectrafitWinRate: 0.8,
      regressions: 0,
      gateState: "PASS",
    },
    trustBlock: { rung: 3, wires: [], n_claims_audited: 3, n_claims_total: 5, nist_validation: null },
    inference: null,
  } as unknown as BenchReport;
}

const baseCtx: PanelCtx = {
  selectedId: "EZ-001",
  view: "case",
  solverIds: ["lmfit", "spectrafit"],
  colors: { lmfit: "#888", spectrafit: "#4af" },
};

// ---------------------------------------------------------------------------
// Tests: happy path — all fields present
// ---------------------------------------------------------------------------

describe("provenanceBody — happy path (all fields present)", () => {
  it("renders winnerReason prominently when present", () => {
    const report = makeReport({
      winnerReason: "spectrafit converged in fewer iterations with lower κ(J)",
      modelSourceFile: "crates/spectrafit-models/src/gaussian.rs",
      modelFormula: "A \\exp(-x^2 / 2\\sigma^2)",
    });
    const node = provenanceBody(report, baseCtx);
    const { container } = render(node as React.ReactElement);
    const text = container.textContent ?? "";
    expect(text).toContain("spectrafit converged in fewer iterations");
  });

  it("renders modelSourceFile path when present", () => {
    const report = makeReport({
      modelSourceFile: "crates/spectrafit-models/src/gaussian.rs",
    });
    const node = provenanceBody(report, baseCtx);
    const { container } = render(node as React.ReactElement);
    const text = container.textContent ?? "";
    expect(text).toContain("crates/spectrafit-models/src/gaussian.rs");
  });

  it("does NOT render modelFormula (formula moved to CaseScenario above the plots)", () => {
    // modelFormula is now rendered by CaseScenario, not by codeProvenance.
    const report = makeReport({
      modelFormula: "A \\exp(-x^2 / 2\\sigma^2)",
      modelSourceFile: "crates/spectrafit-models/src/gaussian.rs",
    });
    const node = provenanceBody(report, baseCtx);
    const { container } = render(node as React.ReactElement);
    const text = container.textContent ?? "";
    // The raw LaTeX string must NOT appear in this panel any more.
    expect(text).not.toContain("A \\exp(-x^2 / 2\\sigma^2)");
  });

  it("renders convergenceEfficiency per backend when present", () => {
    const report = makeReport({
      convergenceEfficiency: 0.0123,
      modelSourceFile: "crates/spectrafit-models/src/gaussian.rs",
    });
    const node = provenanceBody(report, baseCtx);
    const { container } = render(node as React.ReactElement);
    const text = container.textContent ?? "";
    expect(text).toMatch(/0\.012|1\.2e-2|conv/i);
  });

  it("renders ill-conditioned flag when illConditioned=true", () => {
    const report = makeReport({
      illConditioned: true,
      modelSourceFile: "crates/spectrafit-models/src/gaussian.rs",
    });
    const node = provenanceBody(report, baseCtx);
    const { container } = render(node as React.ReactElement);
    const text = container.textContent ?? "";
    expect(text.toLowerCase()).toMatch(/ill.?condition/);
  });

  it("does not hardcode any backend id — uses solversOf pattern", () => {
    // Panel must work with an arbitrary backend roster, not assume lmfit/spectrafit.
    const report = {
      ...makeReport({ modelSourceFile: "crates/spectrafit-models/src/gaussian.rs" }),
      solvers: [
        { id: "oracle-A", label: "Oracle A", color: "#f00" },
        { id: "oracle-B", label: "Oracle B", color: "#00f" },
      ],
    } as unknown as BenchReport;
    // Should not throw even with a different roster.
    expect(() => provenanceBody(report, { ...baseCtx, solverIds: ["oracle-A", "oracle-B"] })).not.toThrow();
  });
});

// ---------------------------------------------------------------------------
// Tests: gated-on-data null return
// ---------------------------------------------------------------------------

describe("provenanceBody — gated-on-data null return", () => {
  it("returns null when winnerReason and modelSourceFile are both absent", () => {
    // modelFormula no longer gates this panel (it is handled by CaseScenario).
    const report = makeReport({
      winnerReason: null,
      modelSourceFile: null,
      modelFormula: null,
    });
    const result = provenanceBody(report, baseCtx);
    expect(result).toBeNull();
  });

  it("returns null when no case is selected (selectedId=null and analyzed is empty)", () => {
    const report = {
      ...makeReport(),
      analyzed: [],
    } as unknown as BenchReport;
    const result = provenanceBody(report, { ...baseCtx, selectedId: null });
    expect(result).toBeNull();
  });

  it("does NOT return null when at least modelSourceFile is present", () => {
    const report = makeReport({
      modelSourceFile: "crates/spectrafit-models/src/gaussian.rs",
      winnerReason: null,
      modelFormula: null,
    });
    const result = provenanceBody(report, baseCtx);
    expect(result).not.toBeNull();
  });

  it("does NOT return null when at least winnerReason is present", () => {
    const report = makeReport({
      winnerReason: "spectrafit was faster",
      modelSourceFile: null,
      modelFormula: null,
    });
    const result = provenanceBody(report, baseCtx);
    expect(result).not.toBeNull();
  });

  it("never leaks 'null' or 'undefined' literal strings into the DOM", () => {
    const report = makeReport({
      winnerReason: "spectrafit won on speed",
      modelSourceFile: null,
      modelFormula: null,
      convergenceEfficiency: null,
      illConditioned: null,
    });
    const node = provenanceBody(report, baseCtx);
    const { container } = render(node as React.ReactElement);
    const text = container.textContent ?? "";
    expect(text).not.toContain("null");
    expect(text).not.toContain("undefined");
  });
});

// ---------------------------------------------------------------------------
// Tests: empty / not-recorded state reads like a human wrote it (Kare)
// ---------------------------------------------------------------------------

describe("provenanceBody — Kare: empty state is human-readable", () => {
  it("absent convergenceEfficiency does not show a raw null or dash placeholder", () => {
    const report = makeReport({
      modelSourceFile: "crates/spectrafit-models/src/gaussian.rs",
      convergenceEfficiency: null,
    });
    const node = provenanceBody(report, baseCtx);
    const { container } = render(node as React.ReactElement);
    const text = container.textContent ?? "";
    // The null branch should not produce literal "null" or "—null"
    expect(text).not.toContain("null");
  });
});

// ---------------------------------------------------------------------------
// Fix D — Wave C1: redChi2Weighted + metricUndefinedReason
// ---------------------------------------------------------------------------

function makeReportWithChi2(opts: {
  redChi2Weighted?: number | null;
  metricUndefinedReason?: string | null;
}): BenchReport {
  const base = makeReport({ modelSourceFile: "crates/spectrafit-models/src/gaussian.rs" });
  // Inject redChi2Weighted / metricUndefinedReason into both backend metric rows.
  const suite = (base.suite ?? []).map((row: any) => ({
    ...row,
    m: {
      lmfit: {
        ...row.m.lmfit,
        redChi2Weighted: opts.redChi2Weighted ?? null,
        metricUndefinedReason: opts.metricUndefinedReason ?? null,
      },
      spectrafit: {
        ...row.m.spectrafit,
        redChi2Weighted: opts.redChi2Weighted ?? null,
        metricUndefinedReason: opts.metricUndefinedReason ?? null,
      },
    },
  }));
  return { ...base, suite } as unknown as BenchReport;
}

describe("provenanceBody — Fix D: redChi2Weighted + metricUndefinedReason", () => {
  it("renders redChi2Weighted per backend when present (not null)", () => {
    const report = makeReportWithChi2({ redChi2Weighted: 1.23 });
    const node = provenanceBody(report, baseCtx);
    const { container } = render(node as React.ReactElement);
    const text = container.textContent ?? "";
    expect(text).toMatch(/χ²_w|chi2_w|1\.23|redChi2/i);
  });

  it("renders metricUndefinedReason when redChi2Weighted is null (noiseless case)", () => {
    const report = makeReportWithChi2({
      redChi2Weighted: null,
      metricUndefinedReason: "χ²_w n/a · noiseless",
    });
    const node = provenanceBody(report, baseCtx);
    const { container } = render(node as React.ReactElement);
    const text = container.textContent ?? "";
    expect(text).toMatch(/noiseless|n\/a|χ²_w/i);
  });

  it("does not render literal null when redChi2Weighted=null and reason=null", () => {
    const report = makeReportWithChi2({ redChi2Weighted: null, metricUndefinedReason: null });
    const node = provenanceBody(report, baseCtx);
    const { container } = render(node as React.ReactElement);
    const text = container.textContent ?? "";
    expect(text).not.toContain("null");
    expect(text).not.toContain("undefined");
  });
});
