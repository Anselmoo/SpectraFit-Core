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
import { Badge } from "../ui/Badge";

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
        gap: "var(--space-2) var(--space-3)",
        padding: "var(--space-3) var(--space-4)",
        fontFamily: "var(--font-mono)",
        fontSize: "0.92rem",
        color: "var(--text-secondary)",
        lineHeight: 1.6,
      }}
    >
      {m.gateState != null && (
        <Badge tone={m.gateState === "pass" ? "success" : m.gateState === "warn" ? "warning" : "danger"}>
          {m.gateState}
        </Badge>
      )}
      <span>
        geomean speedup vs <span style={{ color: "var(--text-primary)" }}>{baseline}</span>{" "}
        <strong style={{ color: "var(--text-primary)" }}>{m.geomeanSpeedupVsBaseline.toFixed(2)}×</strong>
        {" "}· max |Δr²| {m.maxAbsDeltaR2.toExponential(2)}
        {" "}· subject win rate (composite){" "}
        <strong style={{ color: "var(--text-primary)" }}>{(m.spectrafitWinRate * 100).toFixed(1)}%</strong>
        {" "}— measured ratios, not a ranked verdict; a different backend leads under bootstrap resampling (see Winner stability).
      </span>
    </div>
  );
}
