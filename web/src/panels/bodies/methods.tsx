/**
 * Audit (methods) destination body functions — verification wire matrix, NIST
 * validation, cherry-pick, reproduce. TaxonomyPanel is its own file; left as-is.
 */
import { Fragment, useState } from "react";
import type { ReactNode } from "react";
import type { BenchReport } from "../../contract";
import { WireMatrix, wiresOf } from "../../narrative";
import type { WireRow } from "../../narrative";

// ---------------------------------------------------------------------------
// Claim-group definitions (Dye — hierarchy / the verification tree).
// Maps wire-id prefixes to a human claim label. Derived from the claim
// ledger (claims.py) so the grouping matches what the backend audits.
// The ordering reflects the value-stream: from raw arithmetic up to external
// independent replication.
// ---------------------------------------------------------------------------
interface ClaimGroup {
  label: string;
  wireIds: string[];
}

const CLAIM_GROUPS: ClaimGroup[] = [
  {
    label: "Accuracy — metrics & uncertainty",
    wireIds: ["W1", "W2a", "W2b", "W2c", "W2d"],
  },
  {
    label: "Contract integrity",
    wireIds: ["W3", "W4"],
  },
  {
    label: "Render fidelity",
    wireIds: ["W5"],
  },
  {
    label: "Gate values (headline)",
    wireIds: ["W6"],
  },
  {
    label: "Reproducibility — statistical inference",
    wireIds: ["W7", "W10", "W11"],
  },
  {
    label: "External independent validation",
    wireIds: ["W8"],
  },
];

// ===========================================================================
// Audit — verification wire matrix (bespoke card; rendered bare)
// ===========================================================================

export function wireMatrixCard(report: BenchReport): ReactNode {
  const tb = report.trustBlock;

  // Build the verification tree: sort wires into claim groups (Dye — hierarchy).
  // Wires not matched by any group fall into an "ungrouped" bucket shown last.
  function groupWires(allWires: WireRow[]): Array<{ group: ClaimGroup | null; wires: WireRow[] }> {
    const placed = new Set<string>();
    const groups: Array<{ group: ClaimGroup | null; wires: WireRow[] }> = [];
    for (const g of CLAIM_GROUPS) {
      const matched = allWires.filter((w) => g.wireIds.includes(w.id));
      if (matched.length > 0) {
        groups.push({ group: g, wires: matched });
        matched.forEach((w) => placed.add(w.id));
      }
    }
    const ungrouped = allWires.filter((w) => !placed.has(w.id));
    if (ungrouped.length > 0) groups.push({ group: null, wires: ungrouped });
    return groups;
  }

  return (
    <div className="glass" style={{ padding: "var(--s6)" }}>
      {/* Tog — orientation: one-line reader guide at the top of the first card */}
      <p
        data-audit-orientation
        style={{
          margin: "0 0 var(--s4)",
          fontSize: "0.76rem",
          color: "var(--ink-faint)",
          fontFamily: "var(--font-mono)",
          lineHeight: 1.5,
          fontStyle: "italic",
        }}
      >
        Verification evidence — each wire backs a load-bearing claim. The verdict (rung, gate state) lives on{" "}
        <a href="#standing" style={{ color: "var(--accent)", textDecoration: "none" }}>
          Standing ↑
        </a>
        .
      </p>
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
        Verification wires
      </h2>
      {tb != null ? (
        <>
          {/* Dye — verification tree: wires grouped under the claim they support */}
          {groupWires(wiresOf(tb)).map(({ group, wires: groupWires }, gi) => (
            <div
              key={group?.label ?? "__ungrouped__"}
              data-claim-group={group?.label ?? "other"}
              style={{
                marginBottom: gi < CLAIM_GROUPS.length - 1 ? "var(--s4)" : 0,
              }}
            >
              <div
                style={{
                  fontSize: "0.72rem",
                  fontFamily: "var(--font-mono)",
                  fontWeight: 600,
                  letterSpacing: "0.05em",
                  textTransform: "uppercase",
                  color: "var(--ink-faint)",
                  margin: "0 0 var(--s2)",
                }}
              >
                {group?.label ?? "Other wires"}
              </div>
              <WireMatrix wires={groupWires} />
            </div>
          ))}
          {tb.n_claims_total > 0 && (
            <p
              style={{
                margin: "var(--s4) 0 0",
                fontSize: "0.76rem",
                color: "var(--ink-faint)",
                fontFamily: "var(--font-mono)",
                lineHeight: 1.5,
              }}
            >
              {tb.n_claims_audited} of {tb.n_claims_total} claims audited
              {tb.n_claims_audited < tb.n_claims_total
                ? ` — ${tb.n_claims_total - tb.n_claims_audited} ${
                    tb.n_claims_total - tb.n_claims_audited === 1 ? "awaits" : "await"
                  } a passing wire`
                : ""}
            </p>
          )}
          <p
            style={{
              margin: "var(--s2) 0 0",
              fontSize: "0.76rem",
              color: "var(--ink-faint)",
              fontFamily: "var(--font-mono)",
              lineHeight: 1.5,
            }}
          >
            W2c passes: κ(J) is verified for spectrafit (the subject); lmfit and jax do not expose
            a Jacobian condition number — a disclosed per-backend oracle limitation, not a subject
            capability gap. W8 (NIST certified validation) passed — see the panel below for the
            dataset-level evidence.
          </p>
        </>
      ) : (
        <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
          No verification wires in this report.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// NIST StRD validation panel — rung-5 evidence (dest: audit, scope: static)
// ---------------------------------------------------------------------------

/**
 * Renders a compact summary table of the NIST StRD certified-value validation
 * results stored in `report.trustBlock.nist_validation` (the W8 evidence block).
 *
 * Layout (per dataset row):
 *   Dataset | Model formula | Params | Min sig figs | Pass ✓/✗
 * An expandable per-parameter sub-table shows certified vs fitted vs sig figs.
 */
export function nistValidationBody(report: BenchReport): ReactNode {
  const nv = report.trustBlock?.nist_validation;
  if (nv == null) {
    return (
      <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
        No NIST validation data in this report.
      </p>
    );
  }
  return <NistValidationCard nv={nv} />;
}

// ---------------------------------------------------------------------------
// NistValidationCard — progressive disclosure (Jobs: compact summary + expand)
// ---------------------------------------------------------------------------
function NistValidationCard({
  nv,
}: {
  nv: NonNullable<NonNullable<BenchReport["trustBlock"]>["nist_validation"]>;
}): ReactNode {
  const [expanded, setExpanded] = useState(false);

  // Derived from the data, not hardcoded: the subset-disclosure footnote names the
  // actual datasets and counts the distinct model formulas so it can never drift
  // from `nv.datasets` (was a static "Gauss1/2/3, Lanczos1 — 2 model families").
  const datasetNames = nv.datasets.map((d) => d.name).join(", ");
  const nFamilies = new Set(nv.datasets.map((d) => d.model)).size;

  const passIcon = (passed: boolean) => (
    <span
      style={{
        color: passed ? "var(--pass)" : "var(--fail)",
        fontWeight: 600,
        fontSize: "0.85rem",
        fontFamily: "var(--font-mono)",
      }}
    >
      {passed ? "✓" : "✗"}
    </span>
  );

  return (
    <div style={{ overflowX: "auto" }}>
      <h2
        style={{
          margin: "0 0 var(--s2)",
          fontFamily: "var(--font-display)",
          fontWeight: 300,
          fontSize: "1.1rem",
          color: "var(--ink)",
          letterSpacing: "-0.01em",
        }}
      >
        NIST StRD — independent certified validation
      </h2>
      {/* Aggregate summary line — always visible (Jobs: above-fold signal) */}
      <p
        style={{
          margin: "0 0 var(--s3)",
          fontSize: "0.82rem",
          color: "var(--ink-faint)",
          fontFamily: "var(--font-mono)",
          lineHeight: 1.5,
        }}
      >
        {nv.datasets.length} dataset{nv.datasets.length !== 1 ? "s" : ""} ·{" "}
        threshold ≥ {nv.threshold_sig_figs} sig figs ·{" "}
        worst case {nv.min_sig_figs.toFixed(2)} sig figs ·{" "}
        overall {passIcon(nv.passed)}
      </p>

      {/* Jobs — progressive disclosure: dataset table collapsed by default */}
      <button
        data-nist-expand
        onClick={() => setExpanded((v) => !v)}
        style={{
          background: "none",
          border: "1px solid var(--hairline)",
          borderRadius: 4,
          color: "var(--accent)",
          cursor: "pointer",
          fontFamily: "var(--font-mono)",
          fontSize: "0.75rem",
          padding: "var(--s1) var(--s3)",
          marginBottom: "var(--s3)",
        }}
        aria-expanded={expanded}
      >
        {expanded ? "▴ Hide dataset detail" : "▾ Show dataset detail"}
        {" "}({nv.datasets.length})
      </button>

      {expanded && (
        <>
          {/* Per-dataset table */}
          <table
            style={{
              borderCollapse: "collapse",
              width: "100%",
              fontSize: "0.8rem",
              fontFamily: "var(--font-mono)",
              color: "var(--ink)",
              margin: "0 0 var(--s4)",
            }}
          >
            <thead>
              <tr style={{ borderBottom: "1px solid var(--hairline)" }}>
                {(["Dataset", "Model", "Params", "Min sig figs", "Pass"] as const).map((h) => (
                  <th
                    key={h}
                    style={{
                      textAlign: "left",
                      padding: "var(--s1) var(--s3)",
                      fontWeight: 600,
                      color: "var(--ink-faint)",
                      fontSize: "0.72rem",
                      letterSpacing: "0.04em",
                      textTransform: "uppercase",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {nv.datasets.map((ds) => (
                // Keyed Fragment: the map's top-level element carries the key, not the
                // inner <tr> (a bare <> shorthand can't take one → React key warning).
                <Fragment key={ds.name}>
                  {/* Dataset summary row */}
                  <tr style={{ borderBottom: "1px solid var(--hairline)" }}>
                    <td
                      style={{
                        padding: "var(--s2) var(--s3)",
                        fontWeight: 600,
                        whiteSpace: "nowrap",
                        color: "var(--ink)",
                      }}
                    >
                      {ds.name}
                    </td>
                    <td
                      style={{
                        padding: "var(--s2) var(--s3)",
                        color: "var(--ink-faint)",
                        maxWidth: "24rem",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                      title={ds.model}
                    >
                      {ds.model}
                    </td>
                    <td style={{ padding: "var(--s2) var(--s3)", textAlign: "center" }}>{ds.n_params}</td>
                    <td
                      style={{
                        padding: "var(--s2) var(--s3)",
                        textAlign: "center",
                        color: ds.min_sig_figs >= nv.threshold_sig_figs ? "var(--pass)" : "var(--fail)",
                        fontWeight: 600,
                      }}
                    >
                      {ds.min_sig_figs.toFixed(2)}
                    </td>
                    <td style={{ padding: "var(--s2) var(--s3)", textAlign: "center" }}>{passIcon(ds.passed)}</td>
                  </tr>
                  {/* Per-parameter sub-rows */}
                  {ds.params.map((p) => (
                    <tr
                      key={`${ds.name}-${p.name}`}
                      style={{ borderBottom: "1px solid color-mix(in srgb, var(--hairline) 50%, transparent)" }}
                    >
                      <td
                        style={{
                          padding: "var(--s1) var(--s3) var(--s1) calc(var(--s3) * 2)",
                          color: "var(--ink-faint)",
                          fontSize: "0.72rem",
                        }}
                      >
                        ↳ {p.name}
                      </td>
                      <td
                        style={{
                          padding: "var(--s1) var(--s3)",
                          color: "var(--ink-faint)",
                          fontSize: "0.72rem",
                        }}
                        colSpan={2}
                      >
                        certified {p.certified.toPrecision(6)} · fitted {p.fitted.toPrecision(6)}
                      </td>
                      <td
                        style={{
                          padding: "var(--s1) var(--s3)",
                          textAlign: "center",
                          fontSize: "0.72rem",
                          color: p.sig_figs_agreed >= nv.threshold_sig_figs ? "var(--pass)" : "var(--warn)",
                        }}
                      >
                        {p.sig_figs_agreed.toFixed(2)}
                      </td>
                      <td />
                    </tr>
                  ))}
                </Fragment>
              ))}
            </tbody>
          </table>
        </>
      )}
      {/* Subset disclosure footnote — always visible */}
      <p
        style={{
          margin: "var(--s3) 0 0",
          fontSize: "0.72rem",
          color: "var(--ink-faint)",
          fontFamily: "var(--font-mono)",
          lineHeight: 1.5,
        }}
      >
        These {nv.datasets.length} dataset{nv.datasets.length !== 1 ? "s" : ""} ({datasetNames}) are a
        narrow subset — {nFamilies} model {nFamilies === 1 ? "family" : "families"} — of{" "}
        {(nv as any).total_available != null ? `${(nv as any).total_available as number} ` : ""}the NIST StRD
        nonlinear-regression datasets, not a representative spread; the rung-5 unlock rests on this set.
        Broader coverage across the StRD suite is planned as future work.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Scope & boundaries — the honest "what we did NOT test" block (C1.2).
// Mirrors the Standing validation-scope card, in detail. Names the two genuine
// gaps (no reduced/nested-model adequacy V&V; no inferential hypothesis test
// behind the rung) plus the data-derived disclosures (narrow NIST subset, κ(J)
// oracle gap, CI-only wires). Gated on trustBlock.
// ---------------------------------------------------------------------------

export function scopeBoundariesCard(report: BenchReport): ReactNode {
  const tb = report.trustBlock;
  if (tb == null) return null;

  const wires = wiresOf(tb);
  const gaps = wires.filter((w) => w.status === "gap");
  const ciOnly = wires.filter((w) => w.status === "skipped");
  const nistN = tb.nist_validation?.datasets?.length ?? 0;
  // Data-derived denominator — read from the contract, never hardcoded.
  const nistTotal: number | null = (tb.nist_validation as any)?.total_available ?? null;

  // Derive W9 state from live data — never hardcoded.
  const w9Case = report.analyzed?.find((f) => f.nestedAdequacy != null);
  const w9Na = w9Case?.nestedAdequacy;
  const w9Pass = w9Na != null && w9Na.recoveredTrueOrderBic === true;

  // Derive W10/W11 inferential state from live data — never hardcoded.
  // A record with skipped===true means insufficient data; treat as not-exercised,
  // not as a fail (aligns with standing.tsx and inferentialHeadline.tsx behavior).
  const cal = report.inference?.calibration ?? null;
  const speed = report.inference?.speedInference ?? null;
  const w10Present = cal != null && !cal.skipped;
  const w11Present = speed != null && !speed.skipped;
  const w10Pass = w10Present && cal!.passed;
  const w11Pass = w11Present && speed!.passed;

  const item = (label: string, body: ReactNode) => (
    <li style={{ marginBottom: "var(--s3)", lineHeight: 1.55 }}>
      <strong style={{ color: "var(--ink)" }}>{label}</strong>
      <span style={{ color: "var(--ink-dim)" }}> — {body}</span>
    </li>
  );

  return (
    <div className="glass" style={{ padding: "var(--s6)" }}>
      <h2
        style={{
          margin: "0 0 var(--s2)",
          fontFamily: "var(--font-display)",
          fontWeight: 300,
          fontSize: "1.1rem",
          color: "var(--ink)",
          letterSpacing: "-0.01em",
        }}
      >
        Scope &amp; boundaries
      </h2>
      <p style={{ margin: "0 0 var(--s4)", fontSize: "0.82rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>
        The credibility rung measures verification completeness, not correctness for your problem.
        These axes are unmeasured and disclosed up front.
      </p>
      <ul style={{ margin: 0, paddingLeft: "1.1rem", fontFamily: "var(--font-mono)", fontSize: "0.84rem" }}>
        {w9Pass
          ? item(
              "Reduced / nested-model adequacy",
              <>
                V&amp;V recovers the true model order (W9, BIC). The reduced (m*−1) model is statistically
                rejected; BIC selects the correct order m*={w9Na!.selectedOrderBic}.
                {w9Na!.selectedOrderAic !== w9Na!.selectedOrderBic && (
                  <> AIC selects order {w9Na!.selectedOrderAic} — AIC/BIC disagree; W9 criterion is BIC-governed.</>
                )}
              </>,
            )
          : item(
              "Reduced / nested-model adequacy",
              <>
                the nested-order oracle (W9) is implemented but not exercised in this report&apos;s run.
                Every case fits the full generative model to its own data; we do not fit a reduced
                (fewer-term) model this run. When exercised, this wire verifies whether the
                likelihood-ratio test rejects the reduced model and whether AIC/BIC recover the true order.
              </>,
            )}
        {w10Pass && w11Pass
          ? item(
              "Inferential tests back the headline (W10/W11)",
              <>
                validated where tested — σ-calibration (W10) and speed significance (W11) both pass.
                Pull coverage {(cal!.coverage * 100).toFixed(1)}% is consistent with the nominal 68.27%
                1σ band (binomial p = {cal!.binomialP < 0.0001 ? "< 0.0001" : cal!.binomialP.toFixed(4)});
                the geomean speedup 95% CI [{speed!.ciLo.toFixed(2)}×, {speed!.ciHi.toFixed(2)}×]
                excludes 1×. The rung is still a completeness checklist — these tests are evidence
                behind the headline, not a replacement for the wire count.
              </>,
            )
          : item(
              "Inferential hypothesis tests implemented (W10/W11) but not exercised",
              <>
                the σ-calibration test (W10) and speed-significance test (W11) are implemented but not
                exercised in this report&apos;s run. The rung is a verification-completeness checklist
                (inspired by ASME V&amp;V credibility levels, not conformant),
                not a statistical test of the headline; the only currently active inferential tests are
                accuracy-parity equivalence (TOST, FDR-controlled) and bootstrap winner-stability, scoped
                to per-case accuracy/speed.
              </>,
            )}
        {nistN > 0 &&
          item(
            "NIST StRD breadth",
            <>
              certified-value reproduction covers <strong style={{ color: "var(--ink)" }}>{nistN}{nistTotal != null ? ` of ${nistTotal}` : ""}</strong>{" "}
              StRD datasets — a narrow subset, not a representative spread (see the NIST panel above).
            </>,
          )}
        {gaps.length > 0 &&
          item(
            "κ(J) oracle gap",
            <>
              verified for the subject; {gaps.map((w) => w.id).join(", ")} report it n/a — lmfit/jax do
              not expose a Jacobian condition number (non-capping, not a failure).
            </>,
          )}
        {ciOnly.length > 0 &&
          item(
            "CI-only wires",
            <>{ciOnly.map((w) => w.id).join(", ")} run in CI, not in the live served report.</>,
          )}
      </ul>
      <p style={{ margin: "var(--s4) 0 0", fontSize: "0.74rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>
        Summarised on the Standing scope card and in LIMITATIONS.md.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Methods rigor — "we don't cherry-pick" (Cycle 4, dest: audit, scope: static)
// ---------------------------------------------------------------------------

/**
 * The outward-facing rigor story: trustworthiness shown through the evidence
 * (resampling, intervals, calibration, disclosed gaps), not asserted as a
 * meta-score. Every figure derives from the contract; subject-blind throughout.
 * This is the data-told replacement for the old credibility-rung-as-hero.
 */
export function cherryPickCard(report: BenchReport): ReactNode {
  const cfg = report.inference?.config;
  const tb = report.trustBlock;
  const nEquiv = report.inference?.equivalence?.length ?? 0;

  const practice = (label: string, body: ReactNode) => (
    <li style={{ marginBottom: "var(--s3)", lineHeight: 1.55 }}>
      <strong style={{ color: "var(--ink)" }}>{label}</strong>
      <span style={{ color: "var(--ink-dim)" }}> — {body}</span>
    </li>
  );

  return (
    <div className="glass" style={{ padding: "var(--s6)" }}>
      <h2
        style={{
          margin: "0 0 var(--s2)",
          fontFamily: "var(--font-display)",
          fontWeight: 300,
          fontSize: "1.1rem",
          color: "var(--ink)",
          letterSpacing: "-0.01em",
        }}
      >
        We don&rsquo;t cherry-pick
      </h2>
      <p style={{ margin: "0 0 var(--s4)", fontSize: "0.82rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>
        Trust earned by the evidence, not asserted as a score — every practice below is in this run&rsquo;s data.
      </p>
      <ul style={{ margin: 0, paddingLeft: "1.1rem", fontFamily: "var(--font-mono)", fontSize: "0.84rem" }}>
        {cfg != null &&
          practice(
            "Resampling",
            <>
              winner stability is bootstrapped over{" "}
              <strong style={{ color: "var(--ink)" }}>{cfg.bootstrapB.toLocaleString()}</strong> resamples
              (seed {cfg.seed}) — a single lucky run can&rsquo;t crown a backend.
            </>,
          )}
        {cfg != null &&
          practice(
            "Intervals, FDR-controlled",
            <>
              accuracy parity is judged by an equivalence test at margin{" "}
              <strong style={{ color: "var(--ink)" }}>{cfg.equivalenceMargin}</strong> across {nEquiv}{" "}
              categor{nEquiv === 1 ? "y" : "ies"}, with the false-discovery rate held at q ={" "}
              <strong style={{ color: "var(--ink)" }}>{cfg.fdrQ}</strong> — not a single hand-picked case.
            </>,
          )}
        {practice(
          "Calibration",
          <>pull coverage is checked against the ±1σ band per case — over-confident uncertainties show up, they aren&rsquo;t hidden.</>,
        )}
        {tb != null &&
          practice(
            "Disclosed gaps",
            <>
              <strong style={{ color: "var(--ink)" }}>
                {tb.n_claims_audited} of {tb.n_claims_total}
              </strong>{" "}
              claims are backed by a passing verification wire; the rest are disclosed open items (see
              the audit wire matrix), not quietly dropped.{" "}
              <a href="#audit" style={{ color: "var(--accent)", textDecoration: "none" }}>
                see the wire matrix ↑
              </a>
            </>,
          )}
      </ul>
    </div>
  );
}

/**
 * Pinned-baseline comparison — shows how the CURRENT run's geomean speedup
 * compares to the pinned baseline run, so a reader can see whether performance
 * moved. Gated: returns null when manifest.pinned is absent.
 *
 * All values derive from the contract; nothing hardcoded.
 */
export function pinnedBaselineCard(report: BenchReport): ReactNode {
  const pinned = report.manifest?.pinned;
  if (pinned == null) return null;

  const pinnedGeomean = pinned.geomeanSpeedupVsBaseline;
  const currentGeomean = report.manifest?.geomeanSpeedupVsBaseline;
  if (currentGeomean == null) return null;

  const delta = currentGeomean - pinnedGeomean;
  const absDelta = Math.abs(delta);
  const threshold = 0.005; // flat band: |Δ| < 0.5%
  const direction = delta > threshold ? "▲" : delta < -threshold ? "▼" : "—";
  const deltaColor =
    delta > threshold
      ? "var(--pass)"
      : delta < -threshold
        ? "var(--fail)"
        : "var(--ink-faint)";

  const row = (k: string, v: ReactNode) => (
    <div style={{ display: "flex", gap: "var(--s3)", padding: "2px 0" }}>
      <span style={{ minWidth: "8.5rem", color: "var(--ink-faint)" }}>{k}</span>
      <span style={{ color: "var(--ink-dim)" }}>{v}</span>
    </div>
  );

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
        Pinned-baseline comparison
      </h2>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
        {row("pinned run", pinned.runId)}
        {row(
          "pinned geomean",
          <span>
            {pinnedGeomean.toFixed(2)}
            <span style={{ color: "var(--ink-faint)" }}>×</span>
          </span>,
        )}
        {row(
          "current geomean",
          <span>
            {currentGeomean.toFixed(2)}
            <span style={{ color: "var(--ink-faint)" }}>×</span>
          </span>,
        )}
        {row(
          "Δ (current − pinned)",
          <span style={{ color: deltaColor, fontWeight: 600 }}>
            {direction} {delta >= 0 ? "+" : ""}
            {absDelta.toFixed(2)}×
          </span>,
        )}
      </div>
    </div>
  );
}

/**
 * Reproduce affordance — the exact command + the pinned-run provenance so a
 * referee can re-run. All fields derive from manifest.pinned + the report head;
 * nothing hardcoded.
 */
export function reproduceCard(report: BenchReport): ReactNode {
  const pinned = report.manifest?.pinned;
  const baseline = report.baselineSolverId;
  const schema = report.schemaVersion;
  const nCases = pinned?.nCases ?? report.suite?.length;

  const row = (k: string, v: ReactNode) => (
    <div style={{ display: "flex", gap: "var(--s3)", padding: "2px 0" }}>
      <span style={{ minWidth: "8.5rem", color: "var(--ink-faint)" }}>{k}</span>
      <span style={{ color: "var(--ink-dim)" }}>{v}</span>
    </div>
  );

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
        Reproduce this run
      </h2>
      <pre
        style={{
          margin: "0 0 var(--s4)",
          padding: "var(--s3) var(--s4)",
          background: "var(--surface-2)",
          border: "1px solid var(--hairline)",
          borderRadius: 6,
          fontFamily: "var(--font-mono)",
          fontSize: "0.82rem",
          color: "var(--ink)",
          overflowX: "auto",
        }}
      >
        uv run spc-bench run{"\n"}uv run spc-bench gate
      </pre>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
        {pinned != null && row("pinned baseline run", pinned.runId)}
        {pinned?.recordedAt != null && row("recorded at", pinned.recordedAt)}
        {nCases != null && row("cases", String(nCases))}
        {baseline != null && row("baseline solver", `${baseline} (speedup = 1.0×)`)}
        {schema != null && row("schema version", String(schema))}
      </div>
      <p style={{ margin: "var(--s4) 0 0", fontSize: "0.74rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)", lineHeight: 1.5 }}>
        The gate fails if geomean speedup vs the baseline &lt; 1× or max |Δr²| (LM-family) &gt; 1e-3.
      </p>
    </div>
  );
}
