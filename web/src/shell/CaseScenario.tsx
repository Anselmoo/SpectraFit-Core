/**
 * CaseScenario — the model → scenario → conditions header for a #case page.
 * Narrative order: equation, scenario, fit conditions/constraints ABOVE the plots.
 * Constraint lines read real contract fields (Invariant 0): fixedParams + exprEdges.
 */
import type { ReactElement } from "react";
import type { BenchReport } from "../contract";
import { analyzedById } from "../contract";
import { Katex } from "../chrome/Katex";
import { constraintLines } from "../panels/bodies/shared";

const labelStyle = {
  margin: "0 0 var(--s1)", fontSize: "0.72rem", fontFamily: "var(--font-mono)",
  letterSpacing: "0.06em", textTransform: "uppercase" as const, color: "var(--ink-faint)",
};

export function CaseScenario({ report, caseId }: { report: BenchReport; caseId: string }): ReactElement | null {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const f = analyzedById(report, caseId) as any;
  if (f == null) return null;
  const formula: string | null = f.modelFormula ?? null;
  const nGrid: number | null = Array.isArray(f.Ngrid) && f.Ngrid.length ? f.Ngrid[f.Ngrid.length - 1] : null;
  const nPeaks: number = Array.isArray(f.peaks) ? f.peaks.length : 0;
  const nParams: number = Array.isArray(f.paramNames) ? f.paramNames.length : 0;
  const constraints = constraintLines(f);
  return (
    <div className="glass" style={{ padding: "var(--s4)", display: "flex", flexDirection: "column", gap: "var(--s4)" }}>
      {formula != null && (<div><p style={labelStyle}>Model</p><Katex tex={formula} display /></div>)}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--s2) var(--s4)", fontFamily: "var(--font-mono)", fontSize: "0.82rem", color: "var(--ink-dim)" }}>
        <span><span style={{ color: "var(--ink-faint)" }}>scenario</span> {f.name}</span>
        {nGrid != null && <span><span style={{ color: "var(--ink-faint)" }}>N</span> {nGrid}</span>}
        <span><span style={{ color: "var(--ink-faint)" }}>noise</span> {f.noise}</span>
        {nPeaks > 0 && <span><span style={{ color: "var(--ink-faint)" }}>peaks</span> {nPeaks}</span>}
        {nParams > 0 && <span><span style={{ color: "var(--ink-faint)" }}>params</span> {nParams}</span>}
      </div>
      {constraints.length > 0 && (
        <div><p style={labelStyle}>Constraints</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--s2)" }}>
            {constraints.map((c) => (<span key={c} style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", color: "var(--ink-dim)", padding: "2px 8px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--surface-2)" }}>{c}</span>))}
          </div>
        </div>
      )}
    </div>
  );
}
