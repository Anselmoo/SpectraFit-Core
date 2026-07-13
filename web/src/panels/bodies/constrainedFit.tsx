/**
 * Constrained-fit showcase body (dest: "evidence", scope: "overview").
 *
 * Surfaces the fixed-parameter (FX) and tied/shared-parameter (TI) cases as a
 * dedicated capability exhibit, instead of leaving them as anonymous rows in
 * the 151-case suite. Every constraint shown comes from REAL contract fields —
 * fixedParams / exprEdges (Invariant 0), never the display name.
 *
 * Gated-on-data: returns null when the served run carries no fixed/tied cases.
 * No hardcoded backend ids — the tie-support disclosure is derived from which
 * backends actually ran the tied cases (solversOf + suite .m membership).
 */
import type { ReactNode } from "react";
import type { BenchReport } from "../../contract";
import { solversOf } from "../../contract";
import type { PanelCtx } from "../types";
import { constraintLines, solverLabelMap } from "./shared";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type AnyRec = any;

export function constrainedFitBody(report: BenchReport, ctx: PanelCtx): ReactNode {
  const analyzed = (report.analyzed ?? []) as AnyRec[];
  const cases = analyzed.filter((f) => f.category === "fixed" || f.category === "tied");
  if (cases.length === 0) return null;

  const suiteById = new Map<string, AnyRec>((report.suite ?? []).map((s: AnyRec) => [s.id, s]));
  const labelMap = solverLabelMap(report);

  // Data-derived tie-support disclosure: a backend that appears in any tied
  // case's suite .m ran (and therefore can express) ties; roster backends absent
  // from every tied case cannot. Derived from data — no hardcoded backend ids.
  const tieSupporting = new Set<string>();
  for (const f of cases.filter((c) => c.category === "tied")) {
    const m = (suiteById.get(f.id)?.m ?? {}) as Record<string, unknown>;
    for (const id of Object.keys(m)) tieSupporting.add(id);
  }
  const tieUnsupported = solversOf(report).filter((id) => !tieSupporting.has(id));

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--s3)" }}>
      {cases.map((f) => {
        const lines = constraintLines(f);
        const winnerReason: string | null = suiteById.get(f.id)?.winnerReason ?? null;
        return (
          <div
            key={f.id}
            className="glass"
            style={{ padding: "var(--s3) var(--s4)", display: "flex", flexDirection: "column", gap: "var(--s2)" }}
          >
            <div style={{ display: "flex", alignItems: "baseline", gap: "var(--s3)", flexWrap: "wrap" }}>
              <a
                href={`#case=${f.id}`}
                onClick={(e) => {
                  if (ctx.openCase) {
                    e.preventDefault();
                    ctx.openCase(f.id);
                  }
                }}
                style={{ color: "var(--accent)", fontFamily: "var(--font-mono)", fontSize: "0.85rem", textDecoration: "none" }}
              >
                {f.id}
              </a>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.8rem", color: "var(--ink-dim)" }}>{f.name}</span>
              <span style={{ fontSize: "0.72rem", color: "var(--ink-faint)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                {f.category}
              </span>
            </div>
            {lines.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--s2)" }}>
                {lines.map((c) => (
                  <span
                    key={c}
                    style={{
                      fontFamily: "var(--font-mono)", fontSize: "0.76rem", color: "var(--ink-dim)",
                      padding: "2px 8px", borderRadius: 999, border: "1px solid var(--hairline)", background: "var(--surface-2)",
                    }}
                  >
                    {c}
                  </span>
                ))}
              </div>
            )}
            {winnerReason != null && (
              <p style={{ margin: 0, fontSize: "0.78rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>{winnerReason}</p>
            )}
          </div>
        );
      })}
      {tieUnsupported.length > 0 && (
        <p className="absent-note" style={{ fontSize: "0.76rem", color: "var(--ink-faint)" }}>
          {tieUnsupported.map((id) => labelMap[id] ?? id).join(" & ")} cannot express parameter ties and are
          excluded from the tied cases — a disclosed oracle limitation, not a subject gap.
        </p>
      )}
    </div>
  );
}
