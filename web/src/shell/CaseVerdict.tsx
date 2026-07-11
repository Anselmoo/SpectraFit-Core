/**
 * CaseVerdict — the one-line per-case verdict atop the drill-down.
 *
 * Subject-blind, data-derived: reads the selected case's per-backend metrics
 * from suite[].m to report convergence count, the fastest backend (by medMs),
 * and the r² spread across backends. A spread < 1e-6 indicates a saturated
 * case where backends are indistinguishable. Renders nothing when the case or
 * its metrics are absent.
 */
import type { ReactElement } from "react";
import type { BenchReport } from "../contract";
import { defaultCaseId } from "../contract";

/** Build a label map from report.solvers — null-safe (returns {} when solvers absent). */
function buildLabelMap(report: BenchReport): Record<string, string> {
  return Object.fromEntries((report.solvers ?? []).map((s) => [s.id, s.label ?? s.id]));
}

/** r² spread below this threshold is considered "saturated" (backends indistinguishable). */
const SATURATED_THRESHOLD = 1e-6;

interface CaseVerdictProps {
  report: BenchReport;
  caseId: string;
}

export function CaseVerdict({ report, caseId }: CaseVerdictProps): ReactElement | null {
  const suiteCase = report.suite?.find((c) => c.id === caseId);
  if (suiteCase == null) return null;
  const labelMap = buildLabelMap(report);

  const entries = Object.entries(suiteCase.m);
  if (entries.length === 0) return null;

  // Convergence: count backends that RAN this case (present in .m) and succeeded.
  // The denominator is the backends that ran — not the global roster — so the
  // count never pretends an absent backend ran. Absent backends are disclosed
  // separately below.
  const total = entries.length;
  const converged = entries.filter(([, m]) => m.success === true).length;

  // Completeness (no silent gaps): a backend on the global roster but absent from
  // this case's .m did not run it — disclose it explicitly as n/a.
  const ranIds = new Set(entries.map(([id]) => id));
  const rosterIds = report.solvers?.map((s) => s.id) ?? [...ranIds];
  const absentIds = rosterIds.filter((id) => !ranIds.has(id));

  // Fastest: backend with the smallest medMs among CONVERGED backends only.
  // A backend that failed to converge (success !== true) is excluded — a fast
  // failure must never be crowned fastest (EF-PANELS-01/02).
  let fastestId: string | null = null;
  let fastestMs = Infinity;
  for (const [id, m] of entries) {
    if (m.success !== true) continue;
    if (typeof m.medMs === "number" && Number.isFinite(m.medMs) && m.medMs < fastestMs) {
      fastestMs = m.medMs;
      fastestId = id;
    }
  }

  // r² spread: max(r²) − min(r²) across backends with finite r².
  const r2s = entries
    .map(([, m]) => m.r2)
    .filter((v): v is number => typeof v === "number" && Number.isFinite(v));
  const spread = r2s.length >= 2 ? Math.max(...r2s) - Math.min(...r2s) : null;
  const saturated = spread != null && spread < SATURATED_THRESHOLD;

  // When the case is saturated (backends indistinguishable), offer a jump to the
  // most-discriminating case so a deep link to a degenerate case doesn't dead-end.
  const discriminatingId = saturated ? defaultCaseId(report) : "";
  const jumpId = discriminatingId && discriminatingId !== caseId ? discriminatingId : null;

  return (
    <div
      className="glass"
      role="status"
      aria-label="case verdict"
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "baseline",
        gap: "var(--s2) var(--s3)",
        padding: "var(--s3) var(--s4)",
        fontFamily: "var(--font-mono)",
        fontSize: "0.92rem",
        color: "var(--ink-dim)",
        lineHeight: 1.6,
      }}
    >
      <span>
        <strong style={{ color: "var(--ink)" }}>
          {converged}/{total}
        </strong>{" "}
        backend{total !== 1 ? "s" : ""} converged
        {fastestId != null && (
          <>
            {" · "}fastest:{" "}
            <strong style={{ color: "var(--ink)" }}>{labelMap[fastestId] ?? fastestId}</strong>
            {" "}({fastestMs.toFixed(2)} ms)
          </>
        )}
        {spread != null && (
          <>
            {" · "}r² spread{" "}
            <strong style={{ color: "var(--ink)" }}>{spread.toExponential(2)}</strong>
          </>
        )}
        {absentIds.length > 0 && (
          <span style={{ color: "var(--ink-faint)" }}>
            {" · "}
            <strong style={{ color: "var(--ink-dim)" }}>{absentIds.join(", ")}</strong>{" "}
            n/a (did not run this case)
          </span>
        )}
      </span>

      {saturated && (
        <span
          aria-label="saturated case"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--s1)",
            padding: "2px 8px",
            borderRadius: 999,
            border: "1px solid var(--hairline)",
            background: "color-mix(in srgb, var(--warn) 12%, transparent)",
            color: "var(--warn)",
            fontSize: "0.74rem",
            fontWeight: 600,
            whiteSpace: "nowrap",
          }}
        >
          saturated — backends indistinguishable
        </span>
      )}

      {jumpId != null && (
        <a
          href={`#case=${jumpId}`}
          style={{
            color: "var(--accent)",
            fontSize: "0.8rem",
            textDecoration: "none",
            whiteSpace: "nowrap",
          }}
        >
          → jump to a discriminating case ({jumpId})
        </a>
      )}
    </div>
  );
}
