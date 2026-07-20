/**
 * Code-provenance + winner-why panel body (Wave B1).
 *
 * Renders for the Evidence `case` sub-view:
 *   - winnerReason (SuiteCase field) — prominently, the "why" sentence
 *   - modelSourceFile (Featured field) — "this number came from THIS code"
 *   - per-backend convergenceEfficiency / illConditioned (SuiteMetric fields) — supporting signals
 *
 * NOTE: modelFormula is now rendered by CaseScenario (above the plots) — this
 * panel no longer claims or renders the formula; it focuses on provenance and
 * winner rationale.
 *
 * Gated-on-data: returns null when winnerReason and modelSourceFile are both
 * absent (no empty shell, no leaked null — Tog).
 * No ?? PRIMARY fallback. No hardcoded backend ids — uses solversOf pattern.
 *
 * Voices: Kare (human-readable empty state), Tog (panel shows exactly what it
 * claims), Dye (hierarchy: verdict first, then source, then supporting signals).
 */
import type { ReactNode } from "react";
import type { BenchReport } from "../../contract";
import type { PanelCtx } from "../types";
import { selectedCase, solverLabelMap } from "./shared";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Safe format for convergenceEfficiency — never leaks "null". */
function fmtEfficiency(v: number | null | undefined): string | null {
  if (v == null || !Number.isFinite(v)) return null;
  return v.toExponential(2);
}

/** Safe format for redChi2Weighted — never leaks "null". */
function fmtChi2Weighted(v: number | null | undefined): string | null {
  if (v == null || !Number.isFinite(v)) return null;
  return v.toFixed(3);
}

// ---------------------------------------------------------------------------
// Body function
// ---------------------------------------------------------------------------

/**
 * Code-provenance + winner-why body for the Evidence `case` sub-view.
 * Registered as PanelRecord id "code-provenance".
 */
export function provenanceBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const f = selectedCase(report, ctx);

  // Resolve the SuiteCase row for this featured case (winnerReason lives there).
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const suiteRow: any = f != null
    ? (report.suite ?? []).find((s: any) => s.id === f.id)
    : undefined;

  const winnerReason: string | null = suiteRow?.winnerReason ?? null;
  const modelSourceFile: string | null = (f as any)?.modelSourceFile ?? null;

  // Gate: nothing honest to show — render nothing.
  // (modelFormula is now rendered by CaseScenario above the plots.)
  if (winnerReason == null && modelSourceFile == null) {
    return null;
  }

  const solverLabel = solverLabelMap(report);
  const { solverIds, colors } = ctx;

  // Collect per-backend supporting signals from the suite row (derive from data —
  // no hardcoded backend ids).
  type BackendSignal = {
    id: string;
    label: string;
    color: string;
    convergenceEfficiency: string | null;
    illConditioned: boolean | null;
    redChi2Weighted: string | null;
    metricUndefinedReason: string | null;
  };

  const backendSignals: BackendSignal[] = solverIds
    .map((id) => {
      const m: any = suiteRow?.m?.[id];
      if (m == null) return null;
      const ce = fmtEfficiency(m.convergenceEfficiency);
      const ic: boolean | null = m.illConditioned ?? null;
      const chi2w = fmtChi2Weighted(m.redChi2Weighted);
      const undef: string | null = m.metricUndefinedReason ?? null;
      // Only include a backend entry when at least one signal is meaningful.
      if (ce == null && ic == null && chi2w == null && undef == null) return null;
      return {
        id,
        label: solverLabel[id] ?? id,
        color: colors[id] ?? "var(--accent)",
        convergenceEfficiency: ce,
        illConditioned: ic,
        redChi2Weighted: chi2w,
        metricUndefinedReason: undef,
      };
    })
    .filter((s): s is BackendSignal => s != null);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--s4)" }}>
      {/* Winner-why — prominently first (Dye: verdict before detail) */}
      {winnerReason != null && (
        <div>
          <p
            style={{
              margin: "0 0 var(--s1)",
              fontSize: "0.72rem",
              fontFamily: "var(--font-mono)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "var(--ink-faint)",
            }}
          >
            Why this winner
          </p>
          <p
            style={{
              margin: 0,
              fontSize: "0.9rem",
              color: "var(--ink)",
              lineHeight: 1.55,
            }}
          >
            {winnerReason}
          </p>
        </div>
      )}

      {/* Source provenance — "this number came from THIS code" (Kare) */}
      {modelSourceFile != null && (
        <div
          style={{
            borderTop: winnerReason != null ? "1px solid var(--hairline)" : undefined,
            paddingTop: winnerReason != null ? "var(--s3)" : undefined,
          }}
        >
          <p
            style={{
              margin: "0 0 var(--s2)",
              fontSize: "0.72rem",
              fontFamily: "var(--font-mono)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "var(--ink-faint)",
            }}
          >
            Kernel source
          </p>
          <p
            style={{
              margin: 0,
              fontFamily: "var(--font-mono)",
              fontSize: "0.82rem",
              color: "var(--ink-dim)",
              wordBreak: "break-all",
            }}
          >
            {modelSourceFile}
          </p>
        </div>
      )}

      {/* Per-backend supporting signals — only when at least one is present */}
      {backendSignals.length > 0 && (
        <div
          style={{
            borderTop: "1px solid var(--hairline)",
            paddingTop: "var(--s3)",
          }}
        >
          <p
            style={{
              margin: "0 0 var(--s2)",
              fontSize: "0.72rem",
              fontFamily: "var(--font-mono)",
              letterSpacing: "0.06em",
              textTransform: "uppercase",
              color: "var(--ink-faint)",
            }}
          >
            Supporting signals
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--s2)" }}>
            {backendSignals.map(({ id, label, color, convergenceEfficiency, illConditioned, redChi2Weighted, metricUndefinedReason }) => (
              <div
                key={id}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--s3)",
                  fontSize: "0.8rem",
                  fontFamily: "var(--font-mono)",
                  color: "var(--ink-dim)",
                }}
              >
                <span
                  style={{
                    display: "inline-block",
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: color,
                    flexShrink: 0,
                  }}
                />
                <span style={{ minWidth: "7rem" }}>{label}</span>
                {convergenceEfficiency != null && (
                  <span title="Mean cost reduction per iteration (convergenceEfficiency)">
                    conv. eff. {convergenceEfficiency}
                  </span>
                )}
                {illConditioned === true && (
                  <span
                    style={{
                      color: "var(--warn)",
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.76rem",
                    }}
                    title="κ(J) ≥ 1e6 — ill-conditioned"
                  >
                    ill-conditioned
                  </span>
                )}
                {redChi2Weighted != null && (
                  <span title="σ-weighted reduced χ² (redChi2Weighted)">
                    χ²_w {redChi2Weighted}
                  </span>
                )}
                {redChi2Weighted == null && metricUndefinedReason != null && (
                  <span
                    style={{ color: "var(--ink-faint)", fontStyle: "italic" }}
                    title={metricUndefinedReason}
                  >
                    {metricUndefinedReason}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
