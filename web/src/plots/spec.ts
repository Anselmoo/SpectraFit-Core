/**
 * PlotSpec — the scientific-plot methodology spine (Invariant P).
 *
 * Every chart panel declares, in ONE place, the scientific question it answers,
 * whether it makes a verdict (`assertive`) or just shows data (`descriptive`),
 * the criterion + provenance that back an assertive claim, and its visual
 * grammar. The consistency suite (`__tests__/plotSpec.test.ts`) derives from this
 * registry: it fails if a chart has no spec, if an assertive plot lacks a
 * criterion + a real provenance id, or if a spec violates the one grammar.
 *
 * This is the visualization analog of the value-provenance spine
 * (`python/oracles/audit/provenance.py`): assertive plots' `provenanceId` must be
 * a `VALUE_PROVENANCE` id whose value is real (no proxy). The grammar fields
 * carry the *target* rules; Phase 4 migrates each plot fn onto them.
 *
 * Grammar law (one rule, no exceptions — enforced by the suite):
 *  - a `log` axis label MUST end with "(log)";
 *  - every axis carries a `unit` ("—" for dimensionless);
 *  - `color` is one of the declared strategies (no hand-rolled palettes);
 *  - uniform affordances (axis-direction arrows, grid-on-value-axis, layout) are
 *    applied by the shared renderer, not per-spec.
 */

export type PlotKind = "assertive" | "descriptive";
export type ColorStrategy = "byBackend" | "sequential" | "single";

export interface AxisSpec {
  label: string;
  scale: "linear" | "log";
  /** Physical unit, or "—" for dimensionless / categorical. */
  unit: string;
}

export interface PlotSpec {
  id: string;
  kind: PlotKind;
  /** The scientific question the plot answers. */
  question: string;
  /** What makes an assertive answer valid (the V&V / oracle). Required iff assertive. */
  criterion: string | null;
  /** VALUE_PROVENANCE id of the plotted quantity. Required + real iff assertive. */
  provenanceId: string | null;
  x: AxisSpec;
  y: AxisSpec;
  color: ColorStrategy;
  /** True when the plot distinguishes real vs reconstructed/proxy data. */
  provenance: boolean;
}

const A = (label: string, scale: "linear" | "log", unit: string): AxisSpec => ({
  label,
  scale,
  unit,
});

// Assertive, grounded chart plots (provenanceId resolves to a real VALUE_PROVENANCE record).
const ASSERTIVE: PlotSpec[] = [
  {
    id: "delta-r2-ci",
    kind: "assertive",
    question: "Is the subject's per-case accuracy equivalent to the baseline?",
    criterion: "seeded bootstrap 95% CI reproduces bit-for-bit (W7)",
    provenanceId: "inference.delta_r2_ci",
    x: A("Δr² vs baseline", "linear", "—"),
    y: A("case", "linear", "—"),
    color: "single",
    provenance: false,
  },
  {
    id: "speedup-ci",
    kind: "assertive",
    question: "Is the subject faster than the baseline per case?",
    criterion: "seeded bootstrap 95% CI reproduces bit-for-bit (W7)",
    provenanceId: "inference.speedup_ci",
    x: A("speedup", "log", "×"),
    y: A("case", "linear", "—"),
    color: "single",
    provenance: false,
  },
  {
    id: "convergence-truth",
    kind: "assertive",
    question: "Does the subject's θ-trajectory converge to the true parameters?",
    criterion: "ground-truth V&V: dₖ decreases to ≤ recovery tol on synthetic cases",
    provenanceId: "convergence.theta_distance",
    x: A("iteration", "linear", "—"),
    y: A("‖θ − θ_true‖ / s", "log", "—"),
    color: "single",
    provenance: false,
  },
];

// Descriptive chart plots — show the data, make no verdict. Honest with provenanceId=null
// (justification = the `question` framing). Some carry a real/reconstructed distinction.
const DESCRIPTIVE: PlotSpec[] = [
  { id: "spectrum", kind: "descriptive", question: "How closely do fitted curves overlay the observed spectrum?", criterion: null, provenanceId: null, x: A("energy", "linear", "arb. units"), y: A("intensity", "linear", "arb. units"), color: "byBackend", provenance: false },
  { id: "residual", kind: "descriptive", question: "What is the residual structure across the spectrum?", criterion: null, provenanceId: null, x: A("energy", "linear", "arb. units"), y: A("residual", "linear", "arb. units"), color: "byBackend", provenance: false },
  { id: "peaks", kind: "descriptive", question: "How do fitted component peaks compose the total?", criterion: null, provenanceId: null, x: A("energy", "linear", "arb. units"), y: A("intensity", "linear", "arb. units"), color: "byBackend", provenance: false },
  { id: "recovery", kind: "descriptive", question: "Where do fitted parameters land relative to truth and the initial guess?", criterion: null, provenanceId: null, x: A("deviation from truth", "linear", "—"), y: A("parameter", "linear", "—"), color: "byBackend", provenance: false },
  { id: "pulls", kind: "descriptive", question: "Do reported uncertainties cover the ±1σ band?", criterion: null, provenanceId: null, x: A("pull (est−truth)/σ", "linear", "σ"), y: A("count", "linear", "—"), color: "byBackend", provenance: false },
  { id: "convergence", kind: "descriptive", question: "How does χ² descend per iteration across backends?", criterion: null, provenanceId: null, x: A("iteration", "linear", "—"), y: A("cost ½·χ²", "log", "—"), color: "byBackend", provenance: true },
  { id: "timing", kind: "descriptive", question: "What is the per-backend solve-time distribution?", criterion: null, provenanceId: null, x: A("solve time", "log", "ms"), y: A("solver", "linear", "—"), color: "byBackend", provenance: false },
  { id: "warmup", kind: "descriptive", question: "How much cold-start overhead amortizes over runs?", criterion: null, provenanceId: null, x: A("cumulative runs", "log", "—"), y: A("per-run time", "linear", "ms"), color: "byBackend", provenance: false },
  { id: "scaling", kind: "descriptive", question: "How does solve time scale with problem size?", criterion: null, provenanceId: null, x: A("N", "log", "points"), y: A("time", "log", "ms"), color: "byBackend", provenance: false },
  { id: "reproducibility", kind: "descriptive", question: "How stable is the iteration count across repeated runs?", criterion: null, provenanceId: null, x: A("runs", "linear", "—"), y: A("iterations", "linear", "—"), color: "byBackend", provenance: false },
  { id: "residual-qq", kind: "descriptive", question: "Do residuals look Gaussian (Q-Q against normal)?", criterion: null, provenanceId: null, x: A("theoretical quantiles", "linear", "σ"), y: A("sample quantiles", "linear", "σ"), color: "byBackend", provenance: false },
  { id: "speedup-dist", kind: "descriptive", question: "What is the spread of per-case speedups?", criterion: null, provenanceId: null, x: A("speedup", "log", "×"), y: A("solver", "linear", "—"), color: "byBackend", provenance: false },
  { id: "iterations", kind: "descriptive", question: "How many iterations does each backend take?", criterion: null, provenanceId: null, x: A("iterations", "linear", "—"), y: A("solver", "linear", "—"), color: "byBackend", provenance: false },
  { id: "conditioning", kind: "descriptive", question: "How well-conditioned is the Jacobian (κ(J)) where exposed?", criterion: null, provenanceId: null, x: A("κ(J)", "log", "—"), y: A("solver", "linear", "—"), color: "byBackend", provenance: false },
  { id: "saturation", kind: "descriptive", question: "On which categories are all backends indistinguishable?", criterion: null, provenanceId: null, x: A("solver", "linear", "—"), y: A("category", "linear", "—"), color: "sequential", provenance: false },
  { id: "success-rate", kind: "descriptive", question: "How often does each backend converge, by category?", criterion: null, provenanceId: null, x: A("category", "linear", "—"), y: A("converged", "linear", "%"), color: "byBackend", provenance: false },
  { id: "perf-profile", kind: "descriptive", question: "What fraction of cases each solver handles within τ× of best (Dolan-Moré)?", criterion: null, provenanceId: null, x: A("performance ratio τ", "log", "×"), y: A("fraction of cases ρ(τ)", "linear", "—"), color: "byBackend", provenance: false },
  { id: "pareto", kind: "descriptive", question: "What is the speed/accuracy non-dominated frontier?", criterion: null, provenanceId: null, x: A("median solve time", "log", "ms"), y: A("R²", "linear", "—"), color: "byBackend", provenance: false },
  { id: "recovery-error-suite", kind: "descriptive", question: "How does parameter recovery error distribute across the suite?", criterion: null, provenanceId: null, x: A("recovery error", "linear", "%"), y: A("solver", "linear", "—"), color: "byBackend", provenance: false },
  { id: "winner-stability", kind: "descriptive", question: "Which backend wins most consistently under resampling?", criterion: null, provenanceId: null, x: A("win fraction (bootstrap)", "linear", "—"), y: A("solver", "linear", "—"), color: "byBackend", provenance: false },
  { id: "info-criteria", kind: "descriptive", question: "How do backends rank by ΔAIC / ΔBIC?", criterion: null, provenanceId: null, x: A("Δ information criterion", "linear", "—"), y: A("solver", "linear", "—"), color: "byBackend", provenance: false },
  { id: "accuracy-dist", kind: "descriptive", question: "How does the reduced-χ² distribution vary across backends for this case?", criterion: null, provenanceId: null, x: A("reduced χ²", "linear", "—"), y: A("solver", "linear", "—"), color: "byBackend", provenance: false },
  // G18 showcases — descriptive: they demonstrate native-kernel capability
  // (synthetic data, disclosed in the panel body), they make no verdict.
  { id: "multidim-projection", kind: "descriptive", question: "Does the native N-D kernel's fitted surface reproduce the multi-dimensional peak (axis-pair projection)?", criterion: null, provenanceId: null, x: A("column index", "linear", "—"), y: A("row index", "linear", "—"), color: "sequential", provenance: false },
  { id: "global-fit-slices", kind: "descriptive", question: "Does ONE shared model jointly fit every dataset slice of the series?", criterion: null, provenanceId: null, x: A("x", "linear", "arb. units"), y: A("intensity", "linear", "arb. units"), color: "sequential", provenance: false },
  { id: "global-fit-kinetics", kind: "descriptive", question: "How do the shared peaks' amplitudes evolve along the dataset axis?", criterion: null, provenanceId: null, x: A("dataset axis", "linear", "—"), y: A("amplitude", "linear", "arb. units"), color: "sequential", provenance: false },
];

function build(specs: PlotSpec[]): Record<string, PlotSpec> {
  const out: Record<string, PlotSpec> = {};
  for (const s of [...specs]) {
    if (out[s.id]) throw new Error(`duplicate PlotSpec id ${s.id}`);
    out[s.id] = s;
  }
  return out;
}

/** The single source of truth: every chart panel → its scientific + grammar spec. */
export const PLOT_SPECS: Record<string, PlotSpec> = build([...ASSERTIVE, ...DESCRIPTIVE]);
