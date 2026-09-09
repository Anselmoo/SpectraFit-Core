/**
 * Panel registry — every dashboard panel as a declarative record.
 *
 * Ported verbatim from the old inline Shell.tsx bodies. Each record carries the
 * EXACT title text the e2e render-audit asserts on, its destination + scope, and
 * a `make(report, ctx)` that reads from `report` / `ctx` instead of closure vars.
 *
 * SVG-factory panels return an SVGSVGElement (mounted via PlotPanel/PlotMount).
 * Composite panels (plot + legend + caption + table) and the Standing/Audit
 * bespoke hero cards return a ReactNode; the renderer wraps plain cards in a
 * PanelCard, while Standing/Audit render their records bare (their JSX already
 * carries the .glass card + internal heading — wrapping would double the h2).
 *
 * Body functions have been split into focused modules under panels/bodies/:
 *   standing.tsx        — dest: "standing" bodies
 *   methods.tsx         — dest: "audit" bodies (TaxonomyPanel stays in its own file)
 *   evidenceOverview.tsx — dest: "evidence", scope: "overview" bodies
 *   evidenceCase.tsx    — dest: "evidence", scope: "case" bodies
 *   shared.tsx          — helpers used by 2+ modules
 */
import type { PanelRecord } from "./types";
// Standing bodies (audit bodies removed — Unit 5)
import { factsLandingCard } from "./bodies/standing";
// nistValidationBody is re-exported for claimEvidenceIntegrity.test.ts which
// imports it directly from this module. The audit panels are gone but this
// function stays importable from the registry as a stable API.
import { nistValidationBody } from "./bodies/methods";
import {
  saturationBody,
  accuracyParityBody,
  suiteTableBody,
  deltaR2CiBody,
  speedupCiBody,
  winnerStabilityBody,
  paretoBody,
  perfProfileBody,
  successRateBody,
  recoveryErrorBody,
  speedupDistBody,
} from "./bodies/evidenceOverview";
import {
  fitBody,
  peaksBody,
  recoveryBody,
  pullsBody,
  convergenceBody,
  convergenceTruthBody,
  timingBody,
  warmupBody,
  scalingBody,
  reproducibilityBody,
  residualQQBody,
  iterationsBody,
  infoCriteriaBody,
  conditioningBody,
  accuracyBody,
} from "./bodies/evidenceCase";
import { provenanceBody } from "./bodies/codeProvenance";
import { constrainedFitBody } from "./bodies/constrainedFit";
import { multidimShowcaseBody } from "./bodies/multidimShowcase";
import { globalFitShowcaseBody } from "./bodies/globalFitShowcase";
import { solverLabelMap } from "./bodies/shared";

// Re-export nistValidationBody: claimEvidenceIntegrity.test.ts imports it from
// this module directly. nistValidationBody reads trustBlock.nistValidation.
export { nistValidationBody };

// ===========================================================================
// The registry
// ===========================================================================

export const PANELS: PanelRecord[] = [
  // ----- Standing (static, bespoke) -----
  // Unit 5: replaced the old gate-verdict + render-truth pair with a single
  // facts-landing card (neutral masthead + backend table + Evidence flow link).
  // The old cards (gateVerdictCard, renderTruthCard) are kept exported for
  // tests that exercise them directly.
  {
    id: "facts-landing",
    dest: "standing",
    scope: "static",
    title: "Measured medians across the suite",
    make: (r) => factsLandingCard(r),
  },

  // Audit destination removed (Unit 5). All dest:"audit" panels dropped.
  // Verification detail is available via GET /api/v1/trust (the ledger endpoint).
  // The audit body functions (wireMatrixCard, nistValidationBody, etc.) remain
  // importable for any surviving tests that exercise them directly.

  // ----- Evidence overview -----
  {
    id: "saturation",
    dest: "evidence",
    scope: "overview",
    section: "sec-finding",
    title: "Saturation map — where solvers are indistinguishable",
    caption: "Green cells mean backends agree (saturated); only the harder cases pull them apart.",
    make: (r, ctx) => saturationBody(r, ctx),
  },
  {
    id: "accuracy-parity",
    dest: "evidence",
    scope: "overview",
    section: "sec-finding",
    title: "Accuracy parity by category",
    caption:
      "Per-category equivalence (FDR-controlled TOST): where the subject matches the baseline within the margin, and the one place it doesn't.",
    make: (r) => accuracyParityBody(r),
  },
  {
    id: "success-rate",
    dest: "evidence",
    scope: "overview",
    section: "sec-finding",
    title: "Success rate by category",
    caption:
      "Fraction of cases each backend solved successfully — the first robustness question a referee asks.",
    make: (r, ctx) => successRateBody(r, ctx),
  },
  {
    id: "suite-table",
    dest: "evidence",
    scope: "overview",
    section: "sec-compare",
    title: "All cases (suite)",
    caption:
      "Every case and every backend, side by side — the full evidence behind the verdict. Click any row to open that case.",
    make: (r, ctx) => suiteTableBody(r, ctx),
  },
  {
    id: "delta-r2-ci",
    dest: "evidence",
    scope: "overview",
    section: "sec-compare",
    title: (r) => {
      const label = solverLabelMap(r)[r.baselineSolverId] ?? r.baselineSolverId;
      return `Per-case Δr² vs ${label} — 95% CI`;
    },
    caption: (r) =>
      `All ${r.suite.length} cases, sorted by |Δr²| — Δr² against the baseline; an interval overlapping zero means equivalent accuracy.`,
    make: (r, ctx) => deltaR2CiBody(r, ctx),
  },
  {
    id: "speedup-ci",
    dest: "evidence",
    scope: "overview",
    section: "sec-compare",
    title: "Per-case speedup — point estimate with 95% CI",
    caption: (r) =>
      `All ${r.suite.length} cases, sorted by speedup magnitude — speedup vs the baseline with its interval; anything to the right of 1× is faster.`,
    make: (r, ctx) => speedupCiBody(r, ctx),
  },
  {
    id: "perf-profile",
    dest: "evidence",
    scope: "overview",
    section: "sec-compare",
    title: "Performance profile (Dolan-Moré)",
    caption:
      "Fraction of cases each backend solves within τ× of the fastest — ρ(1)=how often it's fastest, the plateau=robustness. The standard solver-benchmark figure (Dolan & Moré 2002).",
    make: (r, ctx) => perfProfileBody(r, ctx),
  },
  {
    id: "pareto",
    dest: "evidence",
    scope: "overview",
    section: "sec-compare",
    title: "Speed vs accuracy (Pareto)",
    caption:
      "Every case × backend — upper-left is the ideal trade-off; the line is the non-dominated frontier.",
    make: (r, ctx) => paretoBody(r, ctx),
  },
  {
    id: "recovery-error-suite",
    dest: "evidence",
    scope: "overview",
    section: "sec-compare",
    title: "Parameter error across the suite",
    caption:
      "How far fitted parameters land from the known truth across all cases — tighter and lower is more accurate.",
    make: (r, ctx) => recoveryErrorBody(r, ctx),
  },
  {
    id: "speedup-dist",
    dest: "evidence",
    scope: "overview",
    section: "sec-compare",
    title: "Speedup distribution",
    caption: "The spread behind the geomean — a single number can hide variance; this shows it.",
    make: (r, ctx) => speedupDistBody(r, ctx),
  },
  {
    id: "winner-stability",
    dest: "evidence",
    scope: "overview",
    section: "sec-compare",
    title: "Winner stability (bootstrap)",
    caption:
      "How often each backend wins under resampling — a guard against one run's luck. The headline win-rate is a speed-weighted composite; under bootstrap resampling the most consistent winner is a different backend — spectrafit's edge is speed at matched accuracy, not being the single best optimizer.",
    make: (r, ctx) => winnerStabilityBody(r, ctx),
  },

  // ----- Evidence overview: constrained-fit showcase (FX/TI) -----
  {
    id: "constrained-fit",
    dest: "evidence",
    scope: "overview",
    section: "sec-constrained",
    title: "Constrained fitting — fixed & tied parameters",
    caption:
      "Cases where a parameter is held fixed or shared across peaks — the constrained-fit capability, shown on the FX/TI cases. Constraints are read from the contract (fixedParams / exprEdges), not the case name.",
    make: (r, ctx) => constrainedFitBody(r, ctx),
  },

  // ----- Evidence overview: native-kernel showcases (G18: SP-2 + SP-3) -----
  {
    id: "multidim-showcase",
    dest: "evidence",
    scope: "overview",
    section: "sec-showcase",
    title: "Multi-dimensional fit — native N-D kernel",
    caption:
      "A genuine N-D fit by spectrafit's parametric gaussian_nd kernel (the subject, not an oracle) on synthetic data — the fitted surface's axis-pair projection plus the recovered peak parameters. Read from analyzed[].multidim.",
    make: (r) => multidimShowcaseBody(r),
  },
  {
    id: "global-fit-showcase",
    dest: "evidence",
    scope: "overview",
    section: "sec-showcase",
    title: "Global fit — one shared model across the series",
    caption:
      "A GlobalFitGraph joint fit of a multi-dataset series: peak centers and widths are shared across every slice, per-slice amplitudes recover the kinetics. Read from analyzed[].globalFit.",
    make: (r) => globalFitShowcaseBody(r),
  },

  // ----- Evidence single-case -----
  {
    id: "fit",
    dest: "evidence",
    scope: "case",
    section: "sec-fit",
    title: "Fit — reference vs initial guess vs solvers",
    caption: "Observed points against each backend's fitted curve — closer overlap is a better fit.",
    make: (r, ctx) => fitBody(r, ctx),
  },
  {
    id: "peaks",
    dest: "evidence",
    scope: "case",
    section: "sec-fit",
    title: "Peak contributions",
    caption: "How each fitted component peak stacks up into the total model spectrum.",
    make: (r, ctx) => peaksBody(r, ctx),
  },
  {
    id: "recovery",
    dest: "evidence",
    scope: "case",
    section: "sec-fit",
    title: "Parameter recovery — guess → fit (0 = truth)",
    caption:
      "Each parameter's guess → fit shown as a deviation relative to its own scale, with truth at 0 — landing on the 0 line means recovered. Per-parameter normalization keeps large and small parameters on one fair axis instead of letting the big ones squash the rest.",
    make: (r, ctx) => recoveryBody(r, ctx),
  },
  {
    id: "pulls",
    dest: "evidence",
    scope: "case",
    section: "sec-fit",
    title: "Pull calibration — coverage vs the 1σ band",
    caption: "(fit − truth)/σ — pulls should sit within ±1 if the reported uncertainties are honest.",
    make: (r, ctx) => pullsBody(r, ctx),
  },
  {
    id: "residual-qq",
    dest: "evidence",
    scope: "case",
    section: "sec-fit",
    title: "Residual normality",
    caption:
      "Residuals on the diagonal ⇒ Gaussian-noise model holds — checks residual SHAPE/normality (tail behaviour, skew). Residuals are standardised to unit sd before plotting, so the y=x diagonal cannot reveal σ-miscalibration; use the pull panel for that.",
    make: (r, ctx) => residualQQBody(r, ctx),
  },
  {
    id: "convergence-truth",
    dest: "evidence",
    scope: "case",
    section: "sec-fit",
    title: "Convergence to ground truth",
    caption:
      "spectrafit's scale-normalized distance of the fitted parameters to the known synthetic truth, dₖ = ‖(θₖ − θ_true)/s‖₂, per accepted iteration (log scale; dashed line = recovery tolerance). The real θ-trajectory recorded by the faer LM solver — not a χ² proxy.",
    make: (r, ctx) => convergenceTruthBody(r, ctx),
  },
  {
    id: "convergence",
    dest: "evidence",
    scope: "case",
    section: "sec-perf",
    title: "Convergence — cost vs iteration",
    caption: (r) => {
      // Derive which backends appear with historySource="reconstructed" across
      // the analyzed cases — never hardcode backend ids, so this stays accurate
      // as the roster evolves (EF-PLOTS-08).
      const reconstructed = new Set<string>();
      for (const c of r.analyzed ?? []) {
        for (const [id, p] of Object.entries((c as { profiles?: Record<string, { historySource?: string }> }).profiles ?? {})) {
          if ((p as { historySource?: string }).historySource === "reconstructed") reconstructed.add(id);
        }
      }
      const list = [...reconstructed];
      const suffix =
        list.length > 0
          ? ` (${list.join("/")} ${list.length === 1 ? "is a" : "are"} reconstructed ${list.length === 1 ? "proxy" : "proxies"})`
          : "";
      return `χ² descent per iteration — lower and flatter is settled${suffix}.`;
    },
    make: (r, ctx) => convergenceBody(r, ctx),
  },
  {
    id: "iterations",
    dest: "evidence",
    scope: "case",
    section: "sec-perf",
    title: "Iterations to converge",
    caption: "Fewer iterations to the optimum is a more efficient solver.",
    make: (r, ctx) => iterationsBody(r, ctx),
  },
  {
    id: "info-criteria",
    dest: "evidence",
    scope: "case",
    section: "sec-perf",
    title: "Information criteria (ΔAIC / ΔBIC)",
    caption:
      "Model-selection criteria per backend — lower ΔAIC/ΔBIC is the preferred fit; MAE complements RMSE.",
    make: (r, ctx) => infoCriteriaBody(r, ctx),
  },
  {
    id: "timing",
    dest: "evidence",
    scope: "case",
    section: "sec-perf",
    title: "Timing distribution (ms, log)",
    caption: "Solve time across repetitions — lower and tighter is faster and more consistent.",
    make: (r, ctx) => timingBody(r, ctx),
  },
  {
    id: "warmup",
    dest: "evidence",
    scope: "case",
    section: "sec-perf",
    title: "Cold → hot amortization",
    caption: "First-call versus warmed-up timing — the gap is JIT and allocation overhead.",
    make: (r, ctx) => warmupBody(r, ctx),
  },
  {
    id: "scaling",
    dest: "evidence",
    scope: "case",
    section: "sec-perf",
    title: "Scaling — time vs N (log-log)",
    caption: "Solve time as the problem grows — a flatter slope is better asymptotic behaviour.",
    make: (r, ctx) => scalingBody(r, ctx),
  },
  {
    id: "reproducibility",
    dest: "evidence",
    scope: "case",
    section: "sec-repro",
    title: "Reproducibility — iterations mean ± sd vs runs",
    caption: "Spread of the result across repeated runs — a tighter band is more reproducible.",
    make: (r, ctx) => reproducibilityBody(r, ctx),
  },
  {
    id: "conditioning",
    dest: "evidence",
    scope: "case",
    section: "sec-repro",
    title: "Conditioning — κ(J) and parameter couplings",
    caption: "κ(J), how invertible each solver's last Jacobian was — lower is better-conditioned.",
    make: (r, ctx) => conditioningBody(r, ctx),
  },
  {
    id: "accuracy-dist",
    dest: "evidence",
    scope: "case",
    section: "sec-repro",
    title: "Accuracy — reduced-χ² distribution",
    caption:
      "Per-backend distribution of reduced χ² over repetitions (p5–p75). The dashed line marks χ²_red = 1 — the expected value when the model fits the noise correctly.",
    make: (r, ctx) => accuracyBody(r, ctx),
  },

  // ----- Evidence single-case: code provenance + winner-why (Wave B1) -----
  {
    id: "code-provenance",
    dest: "evidence",
    scope: "case",
    section: "sec-fit",
    title: "Code provenance — source, formula, and winner rationale",
    caption:
      "Where this case's model kernel lives in the codebase, its registered formula, and the data-derived reason why the winner won. Gated-on-data: hidden when none of these fields were recorded.",
    make: (r, ctx) => provenanceBody(r, ctx),
  },
];
