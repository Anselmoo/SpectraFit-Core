/**
 * CaseVerdict — per-case verdict line atop the drill-down.
 * Subject-blind; reads the selected case's per-backend metrics from suite[].m.
 */
import { render, cleanup } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";
import { CaseVerdict } from "./CaseVerdict";
import type { BenchReport } from "../contract";

afterEach(cleanup);

// Stub where a non-spectrafit backend (scipy-ls-lm) is fastest — subject-blindness check.
// r² values differ by > 1e-6 so it is NOT saturated.
const allConvergedReport = {
  suite: [
    {
      id: "RL-002",
      name: "RL-002 lorentz",
      category: "easy",
      difficulty: 1,
      winner: "scipy-ls-lm",
      regression: false,
      m: {
        "scipy-ls-lm": { speedup: 3.0, r2: 0.9990000, redChi2: 1.1, medMs: 0.07, paramErr: 0.001, success: true },
        lmfit:         { speedup: 1.0, r2: 0.9980000, redChi2: 1.2, medMs: 0.21, paramErr: 0.002, success: true },
        spectrafit:    { speedup: 2.5, r2: 0.9970000, redChi2: 1.15, medMs: 0.09, paramErr: 0.0015, success: true },
      },
    },
  ],
} as unknown as BenchReport;

// Stub with r² spread < 1e-6 (saturated — all backends indistinguishable).
const saturatedReport = {
  suite: [
    {
      id: "EZ-001",
      name: "EZ-001 gaussian",
      category: "easy",
      difficulty: 1,
      winner: "spectrafit",
      regression: false,
      m: {
        lmfit:      { speedup: 1.0, r2: 0.999999999, redChi2: 1.0, medMs: 0.30, paramErr: 0.0001, success: true },
        spectrafit: { speedup: 2.0, r2: 0.999999998, redChi2: 1.0, medMs: 0.15, paramErr: 0.0001, success: true },
      },
    },
  ],
} as unknown as BenchReport;

// Stub with a missing case (not in suite) — component should render nothing.
const missingCaseReport = {
  suite: [],
} as unknown as BenchReport;

// Stub with partial convergence (one backend fails).
const partialConvergeReport = {
  suite: [
    {
      id: "ED-005",
      name: "ED-005 edge",
      category: "edge",
      difficulty: 3,
      winner: "lmfit",
      regression: false,
      m: {
        lmfit:      { speedup: 1.0, r2: 0.95, redChi2: 1.8, medMs: 0.50, paramErr: 0.01, success: true },
        spectrafit: { speedup: 0.8, r2: 0.80, redChi2: 3.5, medMs: 0.62, paramErr: 0.05, success: false },
      },
    },
  ],
} as unknown as BenchReport;

// Stub where the global roster (report.solvers) carries jax, but the selected
// case omits it from .m — the silent-backend-gap the completeness invariant
// forbids. analyzed carries a more-discriminating case (RL-009) so the saturated
// jump affordance has a target.
const missingBackendReport = {
  solvers: [
    { id: "spectrafit", color: "#1" },
    { id: "lmfit", color: "#2" },
    { id: "jax", color: "#3" },
  ],
  analyzed: [
    { id: "EZ-001", category: "easy" },
    { id: "RL-009", category: "reality" },
  ],
  suite: [
    {
      id: "RL-002",
      name: "RL-002 lorentz",
      category: "reality",
      difficulty: 2,
      winner: "spectrafit",
      regression: false,
      m: {
        spectrafit: { speedup: 2.5, r2: 0.9970000, redChi2: 1.15, medMs: 0.09, paramErr: 0.0015, success: true },
        lmfit:      { speedup: 1.0, r2: 0.9980000, redChi2: 1.2, medMs: 0.21, paramErr: 0.002, success: true },
        // jax absent — did not run this case
      },
    },
    // A discriminating case (large r² spread) for the saturated jump affordance.
    {
      id: "RL-009",
      name: "RL-009 hard",
      category: "reality",
      difficulty: 4,
      winner: "lmfit",
      regression: false,
      m: {
        spectrafit: { speedup: 2.0, r2: 0.80, redChi2: 2.0, medMs: 0.10, paramErr: 0.02, success: true },
        lmfit:      { speedup: 1.0, r2: 0.95, redChi2: 1.5, medMs: 0.25, paramErr: 0.01, success: true },
      },
    },
  ],
} as unknown as BenchReport;

// Saturated selected case (EZ-001) with a discriminating sibling (RL-009) in
// analyzed — the jump affordance should point at RL-009.
const saturatedWithSiblingReport = {
  solvers: [
    { id: "spectrafit", color: "#1" },
    { id: "lmfit", color: "#2" },
  ],
  analyzed: [
    { id: "EZ-001", category: "easy" },
    { id: "RL-009", category: "reality" },
  ],
  suite: [
    {
      id: "EZ-001",
      name: "EZ-001 gaussian",
      category: "easy",
      difficulty: 1,
      winner: "spectrafit",
      regression: false,
      m: {
        lmfit:      { speedup: 1.0, r2: 0.999999999, redChi2: 1.0, medMs: 0.30, paramErr: 0.0001, success: true },
        spectrafit: { speedup: 2.0, r2: 0.999999998, redChi2: 1.0, medMs: 0.15, paramErr: 0.0001, success: true },
      },
    },
    {
      id: "RL-009",
      name: "RL-009 hard",
      category: "reality",
      difficulty: 4,
      winner: "lmfit",
      regression: false,
      m: {
        spectrafit: { speedup: 2.0, r2: 0.80, redChi2: 2.0, medMs: 0.10, paramErr: 0.02, success: true },
        lmfit:      { speedup: 1.0, r2: 0.95, redChi2: 1.5, medMs: 0.25, paramErr: 0.01, success: true },
      },
    },
  ],
} as unknown as BenchReport;

// Stub where the FAILED backend has the SMALLEST medMs — EF-PANELS-01/02.
// spectrafit: success=false, medMs=0.05 (fastest raw)
// lmfit:      success=true,  medMs=0.40
// The component must crown lmfit, not spectrafit.
const fastFailureReport = {
  solvers: [{ id: "spectrafit", color: "#1" }, { id: "lmfit", color: "#2" }],
  suite: [
    {
      id: "ED-9",
      name: "ED-9 edge",
      category: "edge",
      difficulty: 3,
      winner: "lmfit",
      regression: false,
      m: {
        spectrafit: { speedup: 2, r2: 0.4, redChi2: 5, medMs: 0.05, paramErr: 0.2, success: false }, // fastest BUT failed
        lmfit:      { speedup: 1, r2: 0.95, redChi2: 1.1, medMs: 0.40, paramErr: 0.01, success: true },
      },
    },
  ],
} as unknown as BenchReport;

describe("CaseVerdict", () => {
  test("shows convergence count, fastest backend (non-spectrafit), and its ms", () => {
    const { container } = render(<CaseVerdict report={allConvergedReport} caseId="RL-002" />);
    const text = container.textContent ?? "";
    // All 3 converged
    expect(text).toMatch(/3\/3/);
    // Fastest is scipy-ls-lm at 0.07 ms
    expect(text).toContain("scipy-ls-lm");
    expect(text).toMatch(/0\.07/);
    // No "saturated" note — spread is > 1e-6
    expect(text.toLowerCase()).not.toContain("saturated");
  });

  test("shows 'saturated' note when r² spread < 1e-6", () => {
    const { container } = render(<CaseVerdict report={saturatedReport} caseId="EZ-001" />);
    const text = container.textContent ?? "";
    // Both converged
    expect(text).toMatch(/2\/2/);
    // Saturated note present
    expect(text.toLowerCase()).toContain("saturated");
  });

  test("renders nothing when the case is absent from suite", () => {
    const { container } = render(<CaseVerdict report={missingCaseReport} caseId="NO-SUCH" />);
    expect(container.textContent).toBe("");
  });

  test("shows partial convergence (1/2 backends) and does not crown a subject", () => {
    const { container } = render(<CaseVerdict report={partialConvergeReport} caseId="ED-005" />);
    const text = container.textContent ?? "";
    // 1 out of 2 converged
    expect(text).toMatch(/1\/2/);
    // lmfit is fastest among backends with a medMs value
    expect(text).toContain("lmfit");
  });

  test("subject-blindness: component text never contains literal 'spectrafit' when another backend is fastest", () => {
    // In allConvergedReport scipy-ls-lm is fastest → spectrafit must NOT appear as the fastest label.
    const { container } = render(<CaseVerdict report={allConvergedReport} caseId="RL-002" />);
    // The fastest label shown must be scipy-ls-lm, NOT spectrafit.
    const text = container.textContent ?? "";
    expect(text).toContain("scipy-ls-lm");
    // spectrafit should not appear in this verdict (it's not the fastest here)
    expect(text.toLowerCase()).not.toContain("spectrafit");
  });

  // T3.1 — the saturated state is a prominent, labelled badge, not just prose.
  test("saturated case carries a labelled 'saturated case' badge", () => {
    const { container } = render(<CaseVerdict report={saturatedReport} caseId="EZ-001" />);
    const badge = container.querySelector('[aria-label="saturated case"]');
    expect(badge).not.toBeNull();
    expect(badge?.textContent?.toLowerCase()).toContain("saturated");
  });

  // T3.3 — completeness: a backend on the global roster but absent from the case's
  // .m is disclosed (n/a — did not run this case), never silently dropped. The
  // converged count must not pretend the absent backend ran.
  test("discloses a roster backend that did not run this case (no silent gap)", () => {
    const { container } = render(<CaseVerdict report={missingBackendReport} caseId="RL-002" />);
    const text = container.textContent ?? "";
    // jax is on report.solvers but absent from RL-002.m → explicit n/a disclosure.
    expect(text).toContain("jax");
    expect(text.toLowerCase()).toContain("n/a");
    // The converged count reflects the 2 backends that ran, not the 3-backend roster.
    expect(text).toMatch(/2\/2/);
    expect(text).not.toMatch(/2\/3/);
  });

  test("no n/a disclosure when every roster backend ran the case", () => {
    const { container } = render(<CaseVerdict report={saturatedWithSiblingReport} caseId="EZ-001" />);
    const text = container.textContent ?? "";
    // Roster = {spectrafit, lmfit}; both ran EZ-001 → no n/a clause.
    expect(text.toLowerCase()).not.toContain("n/a");
  });

  // T3.2 — a saturated case offers a jump to the most-discriminating case so the
  // defaultCaseId spread logic isn't bypassed by a deep link.
  test("saturated case offers a jump to a discriminating case", () => {
    const { container } = render(<CaseVerdict report={saturatedWithSiblingReport} caseId="EZ-001" />);
    const jump = container.querySelector('a[href="#case=RL-009"]');
    expect(jump).not.toBeNull();
    expect(jump?.textContent?.toLowerCase()).toMatch(/discriminating|jump/);
  });

  test("no jump affordance when the case is already discriminating", () => {
    const { container } = render(<CaseVerdict report={saturatedWithSiblingReport} caseId="RL-009" />);
    // RL-009 is not saturated → no jump affordance.
    expect(container.querySelector("a[href^='#case=']")).toBeNull();
  });

  // EF-PANELS-01/02 — a backend that FAILED (success: false) but ran fastest
  // must NOT be crowned "fastest". Only converged backends are eligible.
  test("does not crown a fast non-converged backend as fastest", () => {
    const { container } = render(<CaseVerdict report={fastFailureReport} caseId="ED-9" />);
    const text = container.textContent ?? "";
    // spectrafit failed (success: false) — must not appear as fastest
    expect(text).not.toMatch(/fastest:\s*spectrafit/i);
    // lmfit is the fastest CONVERGED backend — it must appear
    expect(text).toMatch(/lmfit/);
  });

  // EF-PANELS-10 — "fastest" backend must display as the human label (from
  // report.solvers), not the raw solver id, matching the display used by every
  // other registry panel via solverLabelMap.
  test("EF-PANELS-10: fastest backend shows the human label, not the raw id", () => {
    // Fixture: scipy-ls-lm is fastest converged, but has a distinct human label.
    const labeledReport = {
      solvers: [
        { id: "scipy-ls-lm", label: "SciPy LM", color: "#1" },
        { id: "lmfit",       label: "lmfit",     color: "#2" },
        { id: "spectrafit",  label: "spectrafit", color: "#3" },
      ],
      suite: [
        {
          id: "RL-002",
          name: "RL-002 lorentz",
          category: "easy",
          difficulty: 1,
          winner: "scipy-ls-lm",
          regression: false,
          m: {
            "scipy-ls-lm": { speedup: 3.0, r2: 0.999, redChi2: 1.1, medMs: 0.07, paramErr: 0.001, success: true },
            lmfit:         { speedup: 1.0, r2: 0.998, redChi2: 1.2, medMs: 0.21, paramErr: 0.002, success: true },
            spectrafit:    { speedup: 2.5, r2: 0.997, redChi2: 1.15, medMs: 0.09, paramErr: 0.0015, success: true },
          },
        },
      ],
    } as unknown as BenchReport;

    const { container } = render(<CaseVerdict report={labeledReport} caseId="RL-002" />);
    const text = container.textContent ?? "";
    // The human label "SciPy LM" must appear (not the raw id "scipy-ls-lm").
    expect(text).toContain("SciPy LM");
    // The raw solver id must NOT appear as the displayed label.
    expect(text).not.toContain("scipy-ls-lm");
  });
});
