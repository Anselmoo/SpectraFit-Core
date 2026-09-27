/**
 * Nested-model adequacy panel body (W9).
 *
 * Renders the nested-order V&V verdict from the first `analyzed` case that
 * carries a populated `nestedAdequacy` block.  When no such case exists
 * (the oracle was not executed for this run), renders an honest "not exercised"
 * note — never a crash or a blank.
 *
 * I-SCOPE-HONEST: the verdict is derived from the live contract fields; the
 * AIC/BIC disagreement is surfaced when present rather than suppressed.
 */
import type { ReactNode, CSSProperties } from "react";
import type { BenchReport } from "../../contract";
import { nestedVerdict, deltaRows } from "../../series/nestedAdequacy";
import type { NestedAdequacy } from "../../series/nestedAdequacy";
import { fmtP } from "../../series/format";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function fmtDelta(x: number): string {
  return (x >= 0 ? "+" : "") + x.toFixed(2);
}


const MONO: CSSProperties = {
  fontFamily: "var(--font-mono)",
};
const ROW_STYLE: CSSProperties = {
  borderBottom: "1px solid var(--border-subtle)",
};
const TH: CSSProperties = {
  textAlign: "left",
  padding: "var(--space-1) var(--space-3)",
  fontWeight: 600,
  color: "var(--text-secondary)",
  fontSize: "0.72rem",
  letterSpacing: "0.04em",
  textTransform: "uppercase" as const,
  whiteSpace: "nowrap" as const,
};
const TD: CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  fontSize: "0.8rem",
  color: "var(--text-secondary)",
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
        border: `1px solid ${pass ? "var(--success)" : "var(--warning)"}`,
        color: pass ? "var(--success)" : "var(--warning)",
        fontWeight: 600,
      }}
    >
      {pass ? "✓" : "✗"}
    </span>
  );
}

function VerdictBlock({ na }: { na: NestedAdequacy }): ReactNode {
  const v = nestedVerdict(na)!;
  const rows = deltaRows(na);

  return (
    <>
      {/* Headline verdict */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          gap: "var(--space-2) var(--space-4)",
          ...MONO,
          fontSize: "0.84rem",
          marginBottom: "var(--space-5)",
        }}
      >
        <span style={{ color: "var(--text-secondary)" }}>True order m*</span>
        <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{v.trueOrder}</span>

        <span style={{ color: "var(--text-secondary)" }}>Reduced (m*−1) rejected</span>
        <span>
          <VerdictBadge pass={v.reducedRejected} />
          <span style={{ color: "var(--text-secondary)", fontSize: "0.76rem", marginLeft: "var(--space-2)" }}>
            LRT p = {fmtP(v.lrtPReducedVsTrue)}
          </span>
        </span>

        <span style={{ color: "var(--text-secondary)" }}>BIC recovers true order</span>
        <span>
          <VerdictBadge pass={v.bicRecovered} />
          <span style={{ color: "var(--text-secondary)", fontSize: "0.76rem", marginLeft: "var(--space-2)" }}>
            selected order {v.selectedOrderBic}
          </span>
        </span>

        <span style={{ color: "var(--text-secondary)" }}>AIC recovers true order</span>
        <span>
          <VerdictBadge pass={v.aicRecovered} />
          <span style={{ color: "var(--text-secondary)", fontSize: "0.76rem", marginLeft: "var(--space-2)" }}>
            selected order {v.selectedOrderAic}
            {!v.aicBicAgree && (
              <span style={{ color: "var(--warning)", marginLeft: "var(--space-2)" }}>
                (AIC over-selects relative to BIC)
              </span>
            )}
          </span>
        </span>

        <span style={{ color: "var(--text-secondary)" }}>AIC / BIC agree</span>
        <span>
          <VerdictBadge pass={v.aicBicAgree} />
        </span>
      </div>

      {/* Delta-criteria table */}
      <p
        style={{
          margin: "0 0 var(--space-3)",
          fontSize: "0.76rem",
          color: "var(--text-secondary)",
          ...MONO,
        }}
      >
        Nested comparison statistics (full − reduced, so negative ΔAIC/ΔBIC = full model preferred):
      </p>
      <table
        style={{
          borderCollapse: "collapse",
          width: "100%",
          fontSize: "0.8rem",
          ...MONO,
          color: "var(--text-primary)",
          marginBottom: "var(--space-4)",
        }}
      >
        <thead>
          <tr style={ROW_STYLE}>
            {(["Comparison", "LRT p", "F p", "ΔAIC", "ΔBIC"] as const).map((h) => (
              <th key={h} style={TH}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} style={ROW_STYLE}>
              <td style={{ ...TD, color: "var(--text-primary)", maxWidth: "22rem", wordBreak: "break-word" as const }}>
                {row.label}
              </td>
              <td style={{ ...TD, textAlign: "right" as const }}>{fmtP(row.lrtP)}</td>
              <td style={{ ...TD, textAlign: "right" as const }}>{fmtP(row.fP)}</td>
              <td style={{ ...TD, textAlign: "right" as const, color: row.dAIC < 0 ? "var(--success)" : "var(--text-secondary)" }}>
                {fmtDelta(row.dAIC)}
              </td>
              <td style={{ ...TD, textAlign: "right" as const, color: row.dBIC < 0 ? "var(--success)" : "var(--text-secondary)" }}>
                {fmtDelta(row.dBIC)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p
        style={{
          margin: "var(--space-3) 0 0",
          fontSize: "0.72rem",
          color: "var(--text-secondary)",
          ...MONO,
          lineHeight: 1.5,
        }}
      >
        W9 criterion (BIC-governed): BIC must recover the true order m*={v.trueOrder} and the reduced model
        must be rejected (LRT p &lt; 0.05). AIC is reported for completeness — its tendency to over-select
        in moderate-N settings is disclosed rather than suppressed.
      </p>
    </>
  );
}

// ---------------------------------------------------------------------------
// Exported body function
// ---------------------------------------------------------------------------

/**
 * Render the nested-model adequacy panel body.
 *
 * Scans `report.analyzed` for the first case carrying a populated
 * `nestedAdequacy` block.  If none is found (oracle not executed this run),
 * renders an honest "not exercised in this report's run" note.
 */
export function nestedAdequacyBody(report: BenchReport): ReactNode {
  // Find the first analyzed case with a populated nestedAdequacy block.
  const naCase = report.analyzed?.find((f) => f.nestedAdequacy != null);
  const na = naCase?.nestedAdequacy ?? null;

  return (
    <div className="glass" style={{ padding: "var(--space-6)" }}>
      <h2
        style={{
          margin: "0 0 var(--space-4)",
          fontFamily: "var(--font-display)",
          fontWeight: 300,
          fontSize: "1.1rem",
          color: "var(--text-primary)",
          letterSpacing: "-0.01em",
        }}
      >
        Nested-model adequacy — order recovery (W9)
      </h2>

      {na != null ? (
        <VerdictBlock na={na} />
      ) : (
        <p
          style={{
            margin: 0,
            fontSize: "0.85rem",
            color: "var(--text-secondary)",
            fontFamily: "var(--font-mono)",
            lineHeight: 1.5,
          }}
        >
          The nested-order oracle is <strong>implemented (W9)</strong> but was{" "}
          <strong>not exercised</strong> in this report's run. When run, this panel shows the
          model-selection verdict: whether the reduced (m*−1) model is statistically rejected by the
          likelihood-ratio test, and whether AIC / BIC identify the true generative order m*.
        </p>
      )}
    </div>
  );
}
