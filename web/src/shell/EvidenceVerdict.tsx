/**
 * EvidenceVerdict — the one-line headline finding atop the results.
 *
 * A published benchmark report leads with the finding, not with a self-trust
 * score. Subject-blind (the gate is "vs baseline" / "subject win rate"), reusing
 * the same manifest fields the Standing gate-verdict card renders — no new
 * contract, no crowned backend. Renders nothing when the manifest is absent.
 */
import type { ReactElement } from "react";
import type { BenchReport } from "../contract";

const GATE_COLOR: Record<string, string> = {
  pass: "var(--pass)",
  warn: "var(--warn, #d98c00)",
  fail: "var(--fail)",
};

export function EvidenceVerdict({ report }: { report: BenchReport }): ReactElement | null {
  const m = report.manifest;
  if (m == null) return null;
  const baseline = report.baselineSolverId;
  return (
    <div
      className="glass"
      role="status"
      aria-label="headline verdict"
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
      {m.gateState != null && (
        <span
          style={{
            fontSize: "0.72rem",
            padding: "2px 8px",
            borderRadius: 4,
            border: `1px solid ${GATE_COLOR[m.gateState] ?? "var(--hairline)"}`,
            color: GATE_COLOR[m.gateState] ?? "var(--ink-dim)",
            textTransform: "uppercase",
            letterSpacing: "0.06em",
          }}
        >
          {m.gateState}
        </span>
      )}
      <span>
        geomean speedup vs <span style={{ color: "var(--ink)" }}>{baseline}</span>{" "}
        <strong style={{ color: "var(--ink)" }}>{m.geomeanSpeedupVsBaseline.toFixed(2)}×</strong>
        {" "}· max |Δr²| {m.maxAbsDeltaR2.toExponential(2)}
        {" "}· subject win rate (composite){" "}
        <strong style={{ color: "var(--ink)" }}>{(m.spectrafitWinRate * 100).toFixed(1)}%</strong>
        {" "}— measured ratios, not a ranked verdict; a different backend leads under bootstrap resampling (see Winner stability).
      </span>
    </div>
  );
}
