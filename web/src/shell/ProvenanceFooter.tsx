/**
 * ProvenanceFooter — a quiet one-line provenance mark that closes the short
 * editorial columns (Standing / Audit). Reads real contract fields:
 *   - run id         ← manifest.pinned.runId  (the pinned-baseline run)
 *   - schema ver     ← report.schemaVersion
 *   - gitCommit      ← report.gitCommit        (short hash, Wave B1)
 *   - gitBranch      ← report.gitBranch         (branch name, Wave B1)
 *   - runTimestampUnix ← report.runTimestampUnix (human timestamp, Wave B1)
 * Not rendered on Evidence (it scrolls). Composition close (Ive) + warmth (Kare).
 * Git fields are gated-on-present (Tog): absent fields emit nothing, never "null".
 */
import type { ReactElement } from "react";
import type { BenchReport } from "../contract";

/** Format a Unix epoch (seconds) to a compact human-readable string.
 *  Example: 1750000000 → "2025-06-15 01:46" (local time) */
function fmtEpoch(unix: number): string {
  const d = new Date(unix * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function ProvenanceFooter({ report }: { report: BenchReport }): ReactElement | null {
  const runId = report.manifest?.pinned?.runId;
  const schema = report.schemaVersion;
  const gitCommit: string | null = (report as any).gitCommit ?? null;
  const gitBranch: string | null = (report as any).gitBranch ?? null;
  const runTimestampUnix: number | null = (report as any).runTimestampUnix ?? null;
  // G5 disclosure: paths the presentation sanitizer coerced to 0.0 when this
  // report was written — non-empty means some rendered zeros are suppressions,
  // not measurements.
  const sanitizedPaths: string[] = report.manifest?.sanitizedValuePaths ?? [];

  // Nothing honest to show without a run id — render nothing rather than a placeholder.
  if (runId == null) return null;

  return (
    <footer className="prov-footer">
      {/* manifest.pinned.runId is the PINNED-BASELINE run — a different run than
          the one rendered (the masthead dates THIS run). Label it so the two
          cannot be confused (G20). */}
      <span title="The pinned perf-baseline run (speedup = 1.0 reference), not the rendered run">
        pinned baseline: {runId}
      </span>
      <span aria-hidden> · </span>
      <span>schema {schema}</span>
      {/* G5: sanitize-suppression disclosure — gated-on-present (Tog) */}
      {sanitizedPaths.length > 0 && (
        <>
          <span aria-hidden> · </span>
          <span
            title={`Non-finite values coerced to 0.0 at: ${sanitizedPaths.join(", ")}`}
          >
            {sanitizedPaths.length} non-finite value
            {sanitizedPaths.length === 1 ? "" : "s"} suppressed (0.0)
          </span>
        </>
      )}
      {/* Git commit short hash — gated-on-present (Tog) */}
      {gitCommit != null && (
        <>
          <span aria-hidden> · </span>
          <span
            style={{ fontFamily: "var(--font-mono)" }}
            title="Git commit at benchmark run time"
          >
            {gitCommit}
          </span>
        </>
      )}
      {/* Git branch — gated-on-present (Tog) */}
      {gitBranch != null && (
        <>
          <span aria-hidden> · </span>
          <span
            style={{ fontFamily: "var(--font-mono)" }}
            title="Git branch at benchmark run time"
          >
            {gitBranch}
          </span>
        </>
      )}
      {/* Human-readable run timestamp — gated-on-present (Tog) */}
      {runTimestampUnix != null && (
        <>
          <span aria-hidden> · </span>
          <span title={`Unix epoch: ${runTimestampUnix}`}>{fmtEpoch(runTimestampUnix)}</span>
        </>
      )}
      {/* External anchor: NIST validation (present when report carries trust data).
          Leads with the EXTERNAL anchor, not a self-score. */}
      <span aria-hidden> · </span>
      <a
        href="/api/v1/trust"
        className="prov-mark"
        style={{ color: "inherit", textDecoration: "none" }}
        title="Verification ledger — trustBlock + inference slice for this run"
      >
        verification ledger ↓
      </a>
    </footer>
  );
}
