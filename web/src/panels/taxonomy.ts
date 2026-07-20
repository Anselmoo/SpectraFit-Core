export interface FailureMode {
  bug: string;
  before: string;
  fix: string;
  guard: string;
  /** A substring guaranteed to appear in dashboard-render-audit.spec.ts. */
  guardId: string;
  /** "track0" = always-visible engine self-catches; "render" = collapsible render-defect catches. */
  category: "track0" | "render";
}

export const FAILURE_MODES: FailureMode[] = [
  // Track-0 self-catches: defects the audit pipeline caught in the benchmark
  // engine itself — before we could claim the dashboard was trustworthy.
  {
    bug: "σ-weighted vs unweighted χ²_red (W2a, Track 0)",
    before:
      "W2a recomputed reduced-χ² σ-weighted while the engine stores it unweighted — a ~10⁴× mismatch on noisy cases, and σ=0 noiseless (optfn) cases drove |Δ| → ∞, capping the trust rung at 2/5",
    fix: "W2a now recomputes χ²_red under the engine's own unweighted definition; σ=0 no longer divides",
    guard: "Gate status reflects corrected accuracy parity (PASS when |Δr²| ≤ gate threshold)",
    // guardId references the Standing neutral masthead test (gate PASS/FAIL) — the
    // Audit wire-matrix test that previously exercised this was removed with the Audit UI.
    guardId: "PASS|FAIL",
    category: "track0",
  },
  {
    bug: "W3 stale cross-run state (W3, Track 0)",
    before:
      "W3 read the pytest lastfailed cache file-level, so a stale round-trip failure for an OLDER run pinned the current run's trust red (run_031 itself passed)",
    fix: "W3 now scopes to the current run id, reflecting only this run's artifact",
    guard: "The standing masthead shows the current run's facts, never stale state",
    // guardId references the Standing neutral masthead test — the Audit wire-matrix
    // test that previously exercised this was removed with the Audit UI.
    guardId: "neutral masthead",
    category: "track0",
  },
  // Render defects: caught by the Playwright render-audit pass.
  {
    bug: "React insertBefore crash",
    before: "EvidencePanel dropped solver lines + residuals on case/view change",
    fix: "PlotMount mounts SVGs via replaceChildren, isolated from React",
    guard: "no console errors on every case × view",
    guardId: "no console errors",
    category: "render",
  },
  {
    bug: "Colorless solver marks",
    before: "var(--c-<solver>) was undefined → fitted curves rendered invisible",
    fix: "restored the OKLCH per-solver palette in tokens.css",
    guard: "solver fit lines resolve to visible colors",
    guardId: "resolve to visible",
    category: "render",
  },
  {
    bug: "barX on a log axis",
    before: "Conditioning panel rendered blank (bars need a 0 baseline log can't give)",
    fix: "κ(J) drawn as dots, which a log scale supports",
    guard: "no present-but-empty panels",
    guardId: "no blank panels",
    category: "render",
  },
  {
    bug: "PlotMount fiber reuse",
    before: "Overview↔Case nav fired a React deps-size warning + showed stale plots",
    fix: "keyed Fragment per branch so React remounts cleanly",
    guard: "in-app navigation stays clean",
    guardId: "in-app navigation",
    category: "render",
  },
];
