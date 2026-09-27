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
import { StatusStrip } from "../ui/StatusStrip";

export function CompletenessBanner({ report }: { report: BenchReport }): ReactElement | null {
  const c = runCompleteness(report);
  if (c.missing.length === 0) return null;
  return (
    <StatusStrip pillLabel="Preview run" ariaLabel="run completeness" style={{ maxWidth: "var(--layout-nav)" }}>
      {c.nCases} {c.nCases === 1 ? "case" : "cases"}. Not recorded in this run:{" "}
      <strong>{c.missing.join(", ")}</strong> — panels that depend on{" "}
      {c.missing.join(" / ")} are omitted or empty, not estimated.
    </StatusStrip>
  );
}
