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
  margin: "0 0 var(--space-1)", fontSize: "0.72rem", fontFamily: "var(--font-mono)",
  letterSpacing: "0.06em", textTransform: "uppercase" as const, color: "var(--text-secondary)",
};

export function CaseScenario({ report, caseId }: { report: BenchReport; caseId: string }): ReactElement | null {
  const f = analyzedById(report, caseId);
  if (f == null) return null;
  const formula: string | null = f.modelFormula ?? null;
  const nGrid: number | null = Array.isArray(f.Ngrid) && f.Ngrid.length ? f.Ngrid[f.Ngrid.length - 1] : null;
  const nPeaks: number = Array.isArray(f.peaks) ? f.peaks.length : 0;
  const nParams: number = Array.isArray(f.paramNames) ? f.paramNames.length : 0;
  const constraints = constraintLines(f);
  return (
    <div className="glass" style={{ padding: "var(--space-4)", display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
      {formula != null && (<div><p style={labelStyle}>Model</p><Katex tex={formula} display /></div>)}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: "0.82rem", color: "var(--text-secondary)" }}>
        <span><span style={{ color: "var(--text-secondary)" }}>scenario</span> {f.name}</span>
        {nGrid != null && <span><span style={{ color: "var(--text-secondary)" }}>N</span> {nGrid}</span>}
        <span><span style={{ color: "var(--text-secondary)" }}>noise</span> {f.noise}</span>
        {nPeaks > 0 && <span><span style={{ color: "var(--text-secondary)" }}>peaks</span> {nPeaks}</span>}
        {nParams > 0 && <span><span style={{ color: "var(--text-secondary)" }}>params</span> {nParams}</span>}
      </div>
      {constraints.length > 0 && (
        <div><p style={labelStyle}>Constraints</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
            {constraints.map((c) => (<span key={c} style={{ fontFamily: "var(--font-mono)", fontSize: "0.78rem", color: "var(--text-secondary)", padding: "2px 8px", borderRadius: 999, border: "1px solid var(--border-subtle)", background: "var(--surface-raised)" }}>{c}</span>))}
          </div>
        </div>
      )}
    </div>
  );
}
