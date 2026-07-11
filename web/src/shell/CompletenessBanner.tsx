/**
 * CompletenessBanner — honest disclosure when the served run is partial.
 *
 * A 15-case quick run with no timing / no convergence-to-truth must NOT read as
 * a finished study. This banner states what the run does and does not contain,
 * derived entirely from presence checks (no hardcoded "of 139"). It renders
 * nothing when the run carries every dimension the panels describe.
 */
import type { ReactElement } from "react";
import type { BenchReport } from "../contract";
import { runCompleteness } from "../contract";

export function CompletenessBanner({ report }: { report: BenchReport }): ReactElement | null {
  const c = runCompleteness(report);
  if (c.missing.length === 0) return null;
  return (
    <div
      className="glass"
      role="status"
      aria-label="run completeness"
      style={{
        width: "100%",
        maxWidth: "var(--layout-nav)",
        padding: "var(--s3) var(--s4)",
        display: "flex",
        alignItems: "baseline",
        gap: "var(--s3)",
        fontFamily: "var(--font-mono)",
        fontSize: "0.8rem",
        color: "var(--ink-dim)",
        borderLeft: "3px solid var(--warn, #d98c00)",
      }}
    >
      <span style={{ fontWeight: 600, color: "var(--ink)" }}>Preview run</span>
      <span>
        {c.nCases} {c.nCases === 1 ? "case" : "cases"}. Not recorded in this run:{" "}
        <strong>{c.missing.join(", ")}</strong> — panels that depend on{" "}
        {c.missing.join(" / ")} are omitted or empty, not estimated.
      </span>
    </div>
  );
}
