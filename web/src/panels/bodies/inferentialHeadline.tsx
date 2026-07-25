/**
 * Inferential-headline panel bodies (W10 + W11).
 *
 * W10 — σ-calibration: is the pull distribution consistent with the nominal 1σ band?
 * W11 — speed significance: is the geomean speedup statistically distinguishable from 1×?
 *
 * Both panels are gated-on-data: when the relevant contract field is absent (oracle not
 * executed this run), they render an honest "not exercised" note — never a crash or a
 * blank, never a bare gap claim.
 *
 * I-SCOPE-HONEST: verdict derives from live contract fields; the KS secondary diagnostic
 * (W10) and Wilcoxon p-value (W11) are surfaced rather than suppressed.
 */
import type { ReactNode, CSSProperties } from "react";
import type { BenchReport } from "../../contract";
import { calibrationRows, speedRows } from "../../series/inferentialHeadline";
import type { VerdictRow } from "../../series/inferentialHeadline";

// ---------------------------------------------------------------------------
// Shared style tokens
// ---------------------------------------------------------------------------

const MONO: CSSProperties = { fontFamily: "var(--font-mono)" };
const ROW_STYLE: CSSProperties = { borderBottom: "1px solid var(--hairline)" };
const TH: CSSProperties = {
  textAlign: "left",
  padding: "var(--s1) var(--s3)",
  fontWeight: 600,
  color: "var(--ink-faint)",
  fontSize: "0.72rem",
  letterSpacing: "0.04em",
  textTransform: "uppercase" as const,
  whiteSpace: "nowrap" as const,
};
const TD: CSSProperties = {
  padding: "var(--s2) var(--s3)",
  fontSize: "0.8rem",
  color: "var(--ink-dim)",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function VerdictBadge({ pass }: { pass: boolean }): ReactNode {
  return (
    <span
      style={{
        ...MONO,
        display: "inline-block",
        fontSize: "0.78rem",
        padding: "1px 7px",
        borderRadius: 4,
        border: `1px solid ${pass ? "var(--pass)" : "var(--warn)"}`,
        color: pass ? "var(--pass)" : "var(--warn)",
        fontWeight: 600,
      }}
    >
      {pass ? "✓" : "✗"}
    </span>
  );
}

function VerdictTable({ rows }: { rows: VerdictRow[] }): ReactNode {
  return (
    <table
      style={{
        borderCollapse: "collapse",
        width: "100%",
        fontSize: "0.8rem",
        ...MONO,
        color: "var(--ink)",
        marginBottom: "var(--s4)",
      }}
    >
      <thead>
        <tr style={ROW_STYLE}>
          {(["Metric", "Value", "Verdict"] as const).map((h) => (
            <th key={h} style={TH}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} style={ROW_STYLE}>
            <td style={{ ...TD, color: "var(--ink)", maxWidth: "20rem" }}>{row.label}</td>
            <td style={{ ...TD, textAlign: "right" as const }}>{row.value}</td>
            <td style={{ ...TD, textAlign: "center" as const }}>
              {row.pass != null ? <VerdictBadge pass={row.pass} /> : <span style={{ color: "var(--ink-faint)" }}>—</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// ---------------------------------------------------------------------------
// W10 — σ-calibration
// ---------------------------------------------------------------------------

/**
 * Render the σ-calibration panel body (W10).
 *
 * Reads `report.inference.calibration`. If absent (oracle not executed this run),
 * renders an honest "not exercised" note.
 */
export function calibrationBody(report: BenchReport): ReactNode {
  const cal = report.inference?.calibration ?? null;
  const rows = calibrationRows(cal);

  return (
    <div className="glass" style={{ padding: "var(--s6)" }}>
      <h2
        style={{
          margin: "0 0 var(--s4)",
          fontFamily: "var(--font-display)",
          fontWeight: 300,
          fontSize: "1.1rem",
          color: "var(--ink)",
          letterSpacing: "-0.01em",
        }}
      >
        σ-calibration — pull coverage (W10)
      </h2>

      {rows != null ? (
        <>
          <VerdictTable rows={rows} />
          <p
            style={{
              margin: "var(--s3) 0 0",
              fontSize: "0.72rem",
              color: "var(--ink-faint)",
              ...MONO,
              lineHeight: 1.5,
            }}
          >
            W10 criterion: binomial p-value testing whether the empirical pull coverage is consistent
            with the nominal 1σ band ({(cal!.nominal * 100).toFixed(2)}%). The KS test is a secondary
            diagnostic — it tests the pull distribution shape (not just mean coverage).
            α = {cal!.alpha} (Bonferroni-corrected family-wise 0.05 across W10 + W11).
          </p>
        </>
      ) : (
        <p
          style={{
            margin: 0,
            fontSize: "0.85rem",
            color: "var(--ink-faint)",
            fontFamily: "var(--font-mono)",
            lineHeight: 1.5,
          }}
        >
          The σ-calibration test is <strong>implemented (W10)</strong> but was{" "}
          <strong>not exercised</strong> in this report&apos;s run. When run, this panel shows whether
          the pull distribution (θ_est − θ_true) / σ_est is consistent with the nominal 68.27%
          1σ coverage — a direct check that the reported uncertainties are honest, not over- or
          under-confident.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// W11 — speed significance
// ---------------------------------------------------------------------------

/**
 * Render the speed-significance panel body (W11).
 *
 * Reads `report.inference.speedInference`. If absent (oracle not executed this run),
 * renders an honest "not exercised" note.
 */
export function speedBody(report: BenchReport): ReactNode {
  const speed = report.inference?.speedInference ?? null;
  const rows = speedRows(speed);

  return (
    <div className="glass" style={{ padding: "var(--s6)" }}>
      <h2
        style={{
          margin: "0 0 var(--s4)",
          fontFamily: "var(--font-display)",
          fontWeight: 300,
          fontSize: "1.1rem",
          color: "var(--ink)",
          letterSpacing: "-0.01em",
        }}
      >
        Speed significance — geomean speedup vs 1× (W11)
      </h2>

      {rows != null ? (
        <>
          <VerdictTable rows={rows} />
          <p
            style={{
              margin: "var(--s3) 0 0",
              fontSize: "0.72rem",
              color: "var(--ink-faint)",
              ...MONO,
              lineHeight: 1.5,
            }}
          >
            W11 criterion: bootstrap 95% CI on the geomean per-case speedup must exclude 1× (excludesOne).
            Sign-test and Wilcoxon signed-rank p-values are secondary diagnostics — they test whether
            more than half the cases favour the best-performing non-baseline backend (≡ spectrafit on
            this roster) over the baseline (not just the geometric mean).
            α = {speed!.alpha} (Bonferroni-corrected family-wise 0.05 across W10 + W11).
          </p>
        </>
      ) : (
        <p
          style={{
            margin: 0,
            fontSize: "0.85rem",
            color: "var(--ink-faint)",
            fontFamily: "var(--font-mono)",
            lineHeight: 1.5,
          }}
        >
          The speed-significance test is <strong>implemented (W11)</strong> but was{" "}
          <strong>not exercised</strong> in this report&apos;s run. When run, this panel shows a bootstrap
          95% confidence interval on the geometric mean per-case speedup of the best-performing
          non-baseline backend against the baseline — a check that the speedup is statistically
          distinguishable from 1× (no improvement).
        </p>
      )}
    </div>
  );
}
