/**
 * Narrative module — credibility-rung ladder + verification-wire matrix.
 *
 * Two PURE components (plain typed props) + one adapter that maps the
 * contract's trustBlock (camelCase field names from openapi.gen.ts) to the
 * component props.
 */
import type { ReactElement } from "react";
import type { TrustBlock } from "../contract";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

// `gap` mirrors the Python WireStatus literal: a disclosed CAPABILITY gap (the
// backend does not expose the input, e.g. κ(J)) — NOT a numerical failure. It is
// rendered with a neutral/amber treatment and does not cap the credibility rung.
export type WireStatus = "pass" | "warn" | "fail" | "skipped" | "gap";

export interface WireRow {
  id: string;
  name: string;
  status: WireStatus;
  evidence: string;
}

// ---------------------------------------------------------------------------
// Status → CSS-variable mapping (tokens from tokens.css)
// ---------------------------------------------------------------------------

const STATUS_VAR: Record<WireStatus, string> = {
  pass: "var(--pass)",
  warn: "var(--warn)",
  fail: "var(--fail)",
  skipped: "var(--ink-faint)",
  // neutral/amber — a disclosed capability gap, deliberately NOT the red fail token.
  gap: "var(--warn)",
};

const STATUS_LABEL: Record<WireStatus, string> = {
  pass: "✓",
  warn: "⚠",
  fail: "✗",
  // "skipped" in this codebase always means CI-only; surface that honestly rather
  // than rendering a silent grey dash that reads as a gap.
  skipped: "CI",
  gap: "n/a — capability gap",
}

// Wire IDs that are intentionally CI-only (status="skipped" in this served view).
// Rendered with a supplementary disclosure tooltip, not as a generic "skipped".
export const WIRE_CI_ONLY_IDS = new Set(["W5"]);;

// ---------------------------------------------------------------------------
// RungLadder — pure component
// ---------------------------------------------------------------------------

// Verification-completeness ladder inspired by ASME V&V credibility levels (not conformant).
// Higher rungs demand stronger evidence; each tooltip names what that rung asserts.
const RUNG_DEFS: Record<number, string> = {
  1: "Rung 1 — reproducibility: hand examples / smoke checks reproduce.",
  2: "Rung 2 — regression tests with tolerances (the current floor here, inspired by ASME V&V, not conformant).",
  3: "Rung 3 — metamorphic / property-based tests + numerical reliability.",
  4: "Rung 4 — synthetic ground-truth recovery with calibrated coverage.",
  5: "Rung 5 — independent differential validation + uncertainty quantification (external replication).",
};

export function RungLadder({
  rung,
  max = 5,
  compact = false,
}: {
  rung: number;
  max?: number;
  /** compact = just the step blocks (no head / gap line) — for the money subscript. */
  compact?: boolean;
}): ReactElement {
  const steps = Array.from({ length: max }, (_, i) => i + 1);
  const blocks = (
    <div className="rung-steps">
      {steps.map((s) => (
        <span
          key={s}
          className="rung-step"
          data-on={s <= rung ? "1" : "0"}
          title={RUNG_DEFS[s]}
          style={{
            background: s <= rung ? "var(--accent)" : "var(--hairline)",
          }}
        />
      ))}
    </div>
  );
  if (compact) {
    return (
      <div className="rung-ladder" data-current={rung} aria-label={`rung ${rung} of ${max}`}>
        {blocks}
        <p className="rung-legend">Verification-completeness ladder (inspired by ASME V&amp;V credibility levels, not conformant): higher rungs need stronger evidence.</p>
      </div>
    );
  }
  return (
    <div className="rung-ladder" data-current={rung}>
      <div className="rung-head">
        <span className="rung-now">{rung} / {max}</span>
        <span className="rung-cap">verification-completeness level</span>
      </div>
      {blocks}
      {rung < max && (
        <p className="rung-gap">
          gap to top: {max - rung} {max - rung === 1 ? "rung" : "rungs"}
        </p>
      )}
      <p className="rung-legend">Verification-completeness ladder (inspired by ASME V&amp;V credibility levels, not conformant): higher rungs need stronger evidence.</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// WireMatrix — pure component
// ---------------------------------------------------------------------------

export function WireMatrix({ wires }: { wires: WireRow[] }): ReactElement {
  return (
    <ul className="wire-matrix" role="list">
      {wires.map((w) => {
        const isCiOnly = w.status === "skipped" && WIRE_CI_ONLY_IDS.has(w.id);
        return (
          <li key={w.id} className="wire-row" data-status={w.status}>
            <span
              className="wire-id"
              style={{ fontFamily: "var(--font-mono)" }}
            >
              {w.id}
            </span>
            <span
              className="wire-dot"
              style={{ background: STATUS_VAR[w.status] }}
              aria-label={isCiOnly ? "verified in CI" : w.status}
              title={isCiOnly ? "verified in CI — not re-run in this served view" : STATUS_LABEL[w.status]}
            />
            <span className="wire-name">{w.name}</span>
            <span className="wire-evidence">
              {isCiOnly ? (
                <>{w.evidence} · <em style={{ color: "var(--ink-faint)" }}>verified in CI, not in this view</em></>
              ) : w.evidence}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

// ---------------------------------------------------------------------------
// Adapter — maps contract trustBlock → WireRow[]
//
// Field names from openapi.gen.ts WireResult schema (camelCase, matching
// every other contract field since the trust_ledger.py alias-generator fix):
//   wireId   string
//   name     string
//   status   "pass" | "warn" | "fail" | "skipped"
//   evidence string
// ---------------------------------------------------------------------------

const VALID_STATUSES = new Set<string>(["pass", "warn", "fail", "skipped", "gap"]);

export function wiresOf(trustBlock: TrustBlock | null | undefined): WireRow[] {
  return (trustBlock?.wires ?? []).map((w) => {
    // Guard: coerce any unrecognised status to "skipped" so STATUS_VAR[status]
    // always resolves to a defined CSS variable (never undefined → invisible dot).
    const status: WireStatus = VALID_STATUSES.has(w.status)
      ? (w.status as WireStatus)
      : "skipped";
    return {
      id: w.wireId,
      name: w.name,
      status,
      evidence: w.evidence,
    };
  });
}
