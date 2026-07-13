/**
 * Standing destination body functions — the bespoke hero cards rendered bare
 * (their JSX already carries the .glass card; no PanelCard wrapper).
 *
 * Unit 5 (facts landing): the old gateVerdictCard + renderTruthCard pair has been
 * replaced by factsLandingCard — a neutral two-column masthead + a subject-blind
 * per-backend results table. The old functions are kept exported for tests that
 * directly import them (shell/standingHeadlineRung.test.tsx, standingAuditNoSvg).
 */
import type { ReactNode, CSSProperties } from "react";
import type { BenchReport } from "../../contract";
import { RungLadder, wiresOf } from "../../narrative";
import { harmonicMeanFromSuite } from "../../series/harmonicMeanSpeedup";
import { backendFacts } from "../../series/backendFacts";
import { GATE_COLOR } from "./shared";

/**
 * Resolve the harmonic mean speedup for the gate-verdict display.
 *
 * Priority:
 * 1. `manifest.harmonicMeanSpeedupVsBaseline` — emitted by the Python engine for
 *    new runs; always accurate (same speedup slice as geomean).
 * 2. Client-side fallback — compute from `suite[].m[subjectId].speedup` for
 *    results.json that predate the field. The subject is identified as the
 *    non-baseline solver with the most speedup data (enumerated via solversOf;
 *    no hardcoded solver id).
 */
function resolveHarmonicMean(report: BenchReport): number | null {
  const m = report.manifest;
  // 1. Prefer the pre-computed field (present in new runs).
  if (m?.harmonicMeanSpeedupVsBaseline != null) {
    return m.harmonicMeanSpeedupVsBaseline;
  }
  // 2. Client-side fallback: find the subject solver (not the baseline) from the
  //    solver roster and compute the harmonic mean from per-case suite speedups.
  const baselineId = report.baselineSolverId;
  const suite: Array<{ m: Record<string, { speedup: number }> }> =
    Array.isArray(report.suite) ? (report.suite as any) : [];
  // Enumerate non-baseline solvers; pick the first one with speedup data.
  const solverIds = report.solvers.map((s) => s.id).filter((id) => id !== baselineId);
  for (const subjectId of solverIds) {
    const hm = harmonicMeanFromSuite(suite, subjectId);
    if (hm != null) return hm;
  }
  return null;
}

export function gateVerdictCard(report: BenchReport): ReactNode {
  const m = report.manifest;
  const tb = report.trustBlock;
  const hmSpeedup = resolveHarmonicMean(report);

  // Compose the speed+rung linked headline phrase (Wave B1 — Part 3).
  // Reads geomean from manifest and rung from trustBlock; derives both from
  // data — never hardcoded. This is the "two views can't contradict" fix:
  // a reader on Standing sees the same rung as Audit shows.
  const speedRungHeadline =
    m != null && tb != null
      ? `${m.geomeanSpeedupVsBaseline.toFixed(2)}× — verified to rung ${tb.rung}`
      : null;

  return (
    <div className="glass" style={{ padding: "var(--s6)" }}>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--s3)", marginBottom: "var(--s4)" }}>
        <h2
          style={{
            margin: 0,
            fontFamily: "var(--font-display)",
            fontWeight: 300,
            fontSize: "1.2rem",
            color: "var(--ink)",
            letterSpacing: "-0.01em",
          }}
        >
          Gate verdict
        </h2>
        {m?.gateState != null && (
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.78rem",
              padding: "2px 8px",
              borderRadius: "4px",
              border: `1px solid ${GATE_COLOR[m.gateState] ?? "var(--hairline)"}`,
              color: GATE_COLOR[m.gateState] ?? "var(--ink-dim)",
              textTransform: "uppercase",
              letterSpacing: "0.06em",
            }}
          >
            {m.gateState}
          </span>
        )}
      </div>

      {/* Speed–rung linked headline (Wave B1, Part 3): links the geomean speedup
          to the verification-completeness level (inspired by ASME V&V credibility
          levels, not conformant) so a reader can't see a great speedup here while
          the rung shows a different level. Quiet/tertiary size (Dye: this is the
          supporting context, not the hero claim — the gate-state badge is the hero). */}
      {speedRungHeadline != null && (
        <p
          style={{
            margin: "0 0 var(--s4)",
            fontFamily: "var(--font-mono)",
            fontSize: "0.88rem",
            color: "var(--ink-dim)",
            lineHeight: 1.4,
          }}
          title={`Geomean speedup vs baseline, at verification-completeness level ${tb!.rung}/5. See verification ledger for the wires.`}
        >
          <a
            href="/api/v1/trust"
            style={{ color: "inherit", textDecoration: "none" }}
            aria-label={`${speedRungHeadline} — see verification ledger for detail`}
          >
            {speedRungHeadline}
          </a>
        </p>
      )}

      {m != null ? (
        <dl
          style={{
            margin: 0,
            display: "grid",
            gridTemplateColumns: "auto 1fr",
            gap: "var(--s2) var(--s4)",
            fontSize: "0.9rem",
          }}
        >
          <dt style={{ color: "var(--ink-faint)", fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
            geomean speedup vs baseline
          </dt>
          <dd style={{ margin: 0, fontFamily: "var(--font-mono)", color: "var(--ink)" }}>
            {m.geomeanSpeedupVsBaseline.toFixed(2)}×
            {hmSpeedup != null && (
              <span
                style={{ color: "var(--ink-dim)", marginLeft: "var(--s2)", fontSize: "0.82em" }}
                title="Harmonic mean — correct aggregate for equal-time comparisons (Eeckhout 2024). Always ≤ geomean for positively-skewed speedup data."
              >
                · harmonic {hmSpeedup.toFixed(2)}×
              </span>
            )}
          </dd>

          <dt style={{ color: "var(--ink-faint)", fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
            max |Δr²|
          </dt>
          <dd style={{ margin: 0, fontFamily: "var(--font-mono)", color: "var(--ink)" }}>
            {m.maxAbsDeltaR2.toExponential(2)}
          </dd>

          <dt style={{ color: "var(--ink-faint)", fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
            subject win rate
            <small
              style={{
                display: "block",
                color: "var(--ink-faint)",
                fontSize: "0.72rem",
                fontFamily: "var(--font-mono)",
                marginTop: 2,
              }}
            >
              subject's composite rate — speed-weighted; see Winner stability for the resampling winner
            </small>
          </dt>
          <dd style={{ margin: 0, fontFamily: "var(--font-mono)", color: "var(--ink)" }}>
            {(m.spectrafitWinRate * 100).toFixed(1)}%
          </dd>

          {m.regressions > 0 && (
            <>
              <dt style={{ color: "var(--ink-faint)", fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
                regressions
              </dt>
              <dd style={{ margin: 0, fontFamily: "var(--font-mono)", color: "var(--fail)" }}>
                {m.regressions}
              </dd>
            </>
          )}

          {/* Verification-completeness level row — links speed to trust in a scannable dl row (Dye) */}
          {tb != null && (
            <>
              <dt style={{ color: "var(--ink-faint)", fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
                verification-completeness level
                <small
                  style={{
                    display: "block",
                    color: "var(--ink-faint)",
                    fontSize: "0.72rem",
                    fontFamily: "var(--font-mono)",
                    marginTop: 2,
                  }}
                >
                  inspired by ASME V&amp;V credibility levels, not conformant —{" "}
                  <a href="/api/v1/trust" style={{ color: "var(--ink-faint)" }}>verification ledger ↓</a>
                </small>
              </dt>
              <dd style={{ margin: 0, fontFamily: "var(--font-mono)", color: "var(--ink)" }}>
                {tb.rung}/5
              </dd>
            </>
          )}
        </dl>
      ) : (
        <p style={{ margin: 0, fontSize: "0.85rem", color: "var(--ink-faint)", fontFamily: "var(--font-mono)" }}>
          No manifest in this report.
        </p>
      )}

      {hmSpeedup != null && (
        <p
          style={{
            margin: "var(--s4) 0 0",
            fontSize: "0.72rem",
            color: "var(--ink-faint)",
            fontFamily: "var(--font-mono)",
            lineHeight: 1.5,
          }}
        >
          Harmonic mean complements geomean (Eeckhout 2024): ≤ geomean for positively-skewed speedup data; the correct aggregate for equal-time comparisons.
        </p>
      )}
    </div>
  );
}

// NIST_STRD_TOTAL removed: denominator is now always derived from
// trustBlock.nist_validation.total_available (data-derived, never hardcoded).

const SCOPE_H3: CSSProperties = {
  margin: "var(--s4) 0 var(--s2)",
  fontFamily: "var(--font-mono)",
  fontSize: "0.74rem",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "var(--ink-faint)",
};
const SCOPE_UL: CSSProperties = {
  margin: 0,
  paddingLeft: "1.1em",
  display: "grid",
  gap: "var(--s2)",
  fontSize: "0.86rem",
  color: "var(--ink-dim)",
  lineHeight: 1.5,
};

/**
 * Validation-scope card (replaces the old rung-as-hero "render-truth" card).
 *
 * I-SCOPE-HONEST: a rendered trust claim must not assert evidence strength beyond
 * what was actually tested. So the headline is the SCOPE — what was validated AND
 * the load-bearing "what we did NOT test" gaps — and the numeric ASME rung is
 * demoted to a labelled subscript ("a verification-completeness score, not a trust
 * guarantee"). The "Not tested" block names the two gaps the benchmark genuinely
 * has: no reduced/nested-model adequacy V&V, and no inferential hypothesis test
 * behind the headline score. Data-derived facts (NIST subset size, disclosed
 * oracle gaps) come from the live trustBlock; the two structural gaps are constant
 * properties of the benchmark design.
 */
export function renderTruthCard(report: BenchReport): ReactNode {
  const tb = report.trustBlock;
  if (tb == null) return null;

  const wires = wiresOf(tb);
  const passed = wires.filter((w) => w.status === "pass");
  const gaps = wires.filter((w) => w.status === "gap");
  const nist = tb.nist_validation;
  const nistN = nist?.datasets?.length ?? 0;
  // Data-derived denominator — read from the contract, never hardcoded.
  const nistTotal: number | null = (nist as any)?.total_available ?? null;

  // Derive W9 state from live data — never hardcoded.
  const w9Case = report.analyzed?.find((f) => f.nestedAdequacy != null);
  const w9Na = w9Case?.nestedAdequacy;
  const w9Pass = w9Na != null && w9Na.recoveredTrueOrderBic === true;

  // Derive W10/W11 inferential state from live data — never hardcoded.
  // A record with skipped===true means insufficient data (< minPulls / < 2 speedups);
  // treat it as not-exercised, not as a fail (same as absent). The engine always emits
  // a populated record (never null) when it ran; null only on old payloads.
  const cal = report.inference?.calibration ?? null;
  const speed = report.inference?.speedInference ?? null;
  const w10Present = cal != null && !cal.skipped;
  const w11Present = speed != null && !speed.skipped;
  const w10Pass = w10Present && cal!.passed;
  const w11Pass = w11Present && speed!.passed;

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
        Validation scope — what we tested, and what we did not
      </h2>

      <h3 style={SCOPE_H3}>Validated where tested</h3>
      <ul style={SCOPE_UL}>
        {nist != null && nistN > 0 && (
          <li>
            NIST StRD external validation — <strong>{nistN}{nistTotal != null ? ` of ${nistTotal}` : ""}</strong> certified
            datasets reproduced to ≥{nist.threshold_sig_figs} significant figures (worst case{" "}
            {nist.min_sig_figs}).
          </li>
        )}
        <li>
          <strong>{tb.n_claims_audited} of {tb.n_claims_total}</strong> dashboard claims are backed by
          a verification wire.
        </li>
        {passed.length > 0 && (
          <li>
            {passed.length} verification {passed.length === 1 ? "wire passes" : "wires pass"} (
            {passed.map((w) => w.id).join(", ")}).
          </li>
        )}
        {w9Pass && (
          <li>
            <strong>Reduced/nested-model adequacy</strong> — V&amp;V recovers the true model order (W9,
            BIC). The reduced (m*−1) model is statistically rejected; BIC selects order{" "}
            {w9Na!.selectedOrderBic}.{" "}
            {w9Na!.selectedOrderAic !== w9Na!.selectedOrderBic && (
              <span>
                AIC selects order {w9Na!.selectedOrderAic} — AIC/BIC disagree (AIC over-selects); the
                W9 criterion is BIC-governed.
              </span>
            )}
          </li>
        )}
        {w10Pass && (
          <li>
            <strong>σ-calibration (W10)</strong> — pull coverage {(cal!.coverage * 100).toFixed(1)}%
            is consistent with the nominal 68.27% 1σ band (binomial p ={" "}
            {cal!.binomialP < 0.0001 ? "< 0.0001" : cal!.binomialP.toFixed(4)}).
          </li>
        )}
        {w11Pass && (
          <li>
            <strong>Speed significance (W11)</strong> — geomean speedup {speed!.geomeanSpeedup.toFixed(2)}×
            with 95% CI [{speed!.ciLo.toFixed(2)}×, {speed!.ciHi.toFixed(2)}×] excludes 1×.
          </li>
        )}
      </ul>

      <h3 style={{ ...SCOPE_H3, color: "var(--warn)" }}>Not tested / open</h3>
      <ul style={SCOPE_UL}>
        {!w9Pass && (
          <li>
            <strong>Reduced/nested-model adequacy V&amp;V</strong> is implemented (W9) but not exercised
            in this report&apos;s run. Every case fits the full model to data generated from that model;
            the nested-order oracle (likelihood-ratio / AIC-BIC) was not executed this run.
          </li>
        )}
        {w10Pass && w11Pass ? (
          <li>
            <strong>Validated where tested — inferential tests back the headline (W10 σ-calibration,
            W11 speed).</strong> Pull coverage is consistent with the nominal 1σ band (binomial p ={" "}
            {cal!.binomialP < 0.0001 ? "< 0.0001" : cal!.binomialP.toFixed(4)}); the geomean speedup
            CI [{speed!.ciLo.toFixed(2)}×, {speed!.ciHi.toFixed(2)}×] excludes 1×.
          </li>
        ) : w10Present || w11Present ? (
          <li>
            <strong>Inferential tests partially exercised.</strong>{" "}
            {w10Present
              ? `W10 σ-calibration: ${w10Pass ? "pass" : "fail"} (coverage ${(cal!.coverage * 100).toFixed(1)}%, p = ${cal!.binomialP.toFixed(4)}).`
              : "W10 σ-calibration: implemented but not exercised in this run."}{" "}
            {w11Present
              ? `W11 speed significance: ${w11Pass ? "pass" : "fail"} (geomean ${speed!.geomeanSpeedup.toFixed(2)}×).`
              : "W11 speed significance: implemented but not exercised in this run."}
          </li>
        ) : (
          <li>
            <strong>No inferential hypothesis test exercised yet.</strong> The σ-calibration
            hypothesis test (W10) and speed-significance hypothesis test (W11) are implemented but
            not exercised in this report&apos;s run. The rung is a checklist of verification wires,
            not a statistical test with a margin and an error rate.
          </li>
        )}
        <li>
          <strong>NIST coverage is a narrow subset</strong> — {nistN}{nistTotal != null ? ` of ${nistTotal}` : ""} StRD
          datasets; many problems (e.g. MGH10) remain unexercised.
        </li>
        {gaps.length > 0 && (
          <li>
            <strong>Disclosed oracle gaps</strong> ({gaps.map((w) => w.id).join(", ")}) — κ(J) is
            verified for the subject; lmfit/jax do not expose it (non-capping, not a failure).
          </li>
        )}
      </ul>

      <a
        href="/api/v1/trust"
        className="rung-deeplink"
        aria-label="Download the verification ledger for this run"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--s3)",
          margin: "var(--s4) 0 0",
          paddingTop: "var(--s3)",
          borderTop: "1px solid var(--hairline)",
          textDecoration: "none",
          color: "inherit",
        }}
      >
        <RungLadder rung={tb.rung} max={5} compact />
        <p
          style={{
            margin: 0,
            fontSize: "0.72rem",
            color: "var(--ink-faint)",
            fontFamily: "var(--font-mono)",
            lineHeight: 1.5,
          }}
        >
          Verification-completeness level {tb.rung}/5 (inspired by ASME V&amp;V credibility levels, not conformant) —{" "}
          <strong style={{ color: "var(--ink-dim)" }}>not a trust guarantee</strong>. It counts how many
          wires pass, not whether the numbers are correct for your problem.{" "}
          <a href="/api/v1/trust" style={{ color: "var(--ink-faint)" }}>verification ledger ↓</a>
        </p>
      </a>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Unit 5 — Facts landing card (replaces the two-card Standing layout)
//
// Neutral two-column masthead + per-backend results table (alphabetical, no row
// crowned). Matches mockup v3 tone: facts, no verdict, no advocacy language.
// Backend count is data-derived from suite[].m membership.
// ---------------------------------------------------------------------------

const PASS_STYLE: CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: "0.72rem",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
  padding: "2px 9px",
  borderRadius: "999px",
  border: "1px solid var(--pass)",
  color: "var(--pass)",
};

const FACT_ROW: CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "baseline",
  gap: "var(--s4)",
  fontFamily: "var(--font-mono)",
  fontSize: "0.9rem",
};

const FACT_KEY: CSSProperties = {
  color: "var(--ink-faint)",
  fontSize: "0.8rem",
};

const FACT_VAL: CSSProperties = {
  color: "var(--ink)",
  fontVariantNumeric: "tabular-nums",
};

const TH_STYLE: CSSProperties = {
  padding: "var(--s4)",
  textAlign: "right",
  color: "var(--ink-faint)",
  fontWeight: 400,
  fontSize: "0.78rem",
  letterSpacing: "0.04em",
  whiteSpace: "nowrap",
};

const TH_FIRST: CSSProperties = {
  ...TH_STYLE,
  textAlign: "left",
};

const TD_STYLE: CSSProperties = {
  padding: "var(--s4)",
  textAlign: "right",
  color: "var(--ink-dim)",
  fontFamily: "var(--font-mono)",
  fontVariantNumeric: "tabular-nums",
  borderBottom: "1px solid var(--hairline)",
};

const TD_FIRST: CSSProperties = {
  ...TD_STYLE,
  textAlign: "left",
  color: "var(--ink)",
};

function fmtMs(v: number | null): string {
  if (v == null) return "—";
  return v < 1 ? `${(v * 1000).toFixed(0)} µs` : `${v.toFixed(2)} ms`;
}

function fmtR2(v: number | null): string {
  if (v == null) return "—";
  return v.toFixed(4);
}

function fmtSpeedup(v: number | null): string {
  if (v == null) return "—";
  return `${v.toFixed(2)}×`;
}

function fmtPct(v: number | null): string {
  if (v == null) return "—";
  return `${(v * 100).toFixed(0)}%`;
}

/**
 * Facts landing card — the new Standing page hero.
 *
 * Replaces the pair of gateVerdictCard + renderTruthCard with a neutral
 * two-column masthead + a subject-blind per-backend results table.
 */
export function factsLandingCard(report: BenchReport): ReactNode {
  const m = report.manifest;
  const facts = backendFacts(report);
  const nCases = report.suite?.length ?? 0;
  const nBackends = facts.length;
  const baseline = report.baselineSolverId;
  // The eyebrow labels THIS run by its own date (from runTimestampUnix), never
  // manifest.pinned.runId — that is the *pinned baseline* run, a different run, and
  // showing it here mislabels the report.
  const runDate: string | null = (() => {
    const ts: number | null = (report as any).runTimestampUnix ?? null;
    if (ts == null) return null;
    const d = new Date(ts * 1000);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  })();

  // Check if any backend was declared in the roster but ran 0 cases (e.g. jax).
  const rosterIds = new Set(report.solvers.map((s) => s.id));
  const presentIds = new Set(facts.map((f) => f.id));
  const optionalAbsent = Array.from(rosterIds).filter((id) => !presentIds.has(id));

  return (
    <>
      {/* Two-column masthead */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.5fr 1fr",
          gap: "var(--s7)",
          alignItems: "end",
          marginBottom: "var(--s7)",
        }}
        className="facts-masthead"
      >
        <div>
          <p
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "0.74rem",
              letterSpacing: "0.14em",
              textTransform: "uppercase",
              color: "var(--ink-faint)",
              margin: "0 0 var(--s4)",
            }}
          >
            SpectraFit benchmark{runDate != null ? ` · ${runDate}` : ""}
          </p>
          <h1
            style={{
              fontFamily: "var(--font-display)",
              fontWeight: 300,
              fontSize: "2.4rem",
              lineHeight: 1.12,
              letterSpacing: "-0.015em",
              margin: 0,
              color: "var(--ink)",
            }}
          >
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{nCases}</span> peak-fitting cases,
            <br />
            <span style={{ fontVariantNumeric: "tabular-nums" }}>{nBackends}</span> solver backends, measured.
          </h1>
          <p
            style={{
              fontFamily: "var(--font-body)",
              fontSize: "1rem",
              color: "var(--ink-dim)",
              margin: "var(--s4) 0 0",
              maxWidth: "52ch",
              lineHeight: 1.55,
            }}
          >
            Every backend solved the same suite under matched stopping tolerances.
            The numbers are measured medians across all cases — read them as you like;
            nothing here is crowned.
          </p>
        </div>
        <div
          style={{
            borderLeft: "1px solid var(--hairline)",
            paddingLeft: "var(--s5)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--s3)",
          }}
        >
          {m?.gateState != null && (
            <div style={FACT_ROW}>
              <span style={FACT_KEY}>gate</span>
              <span style={FACT_VAL}>
                {/^pass$/i.test(m.gateState) ? (
                  <span style={PASS_STYLE}>{m.gateState}</span>
                ) : (
                  <span style={{ ...PASS_STYLE, borderColor: "var(--fail)", color: "var(--fail)" }}>
                    {m.gateState}
                  </span>
                )}
              </span>
            </div>
          )}
          <div style={FACT_ROW}>
            <span style={FACT_KEY}>cases</span>
            <span style={FACT_VAL}>{nCases}</span>
          </div>
          <div style={FACT_ROW}>
            <span style={FACT_KEY}>backends measured</span>
            <span style={FACT_VAL}>{nBackends}</span>
          </div>
          <div style={FACT_ROW}>
            <span style={FACT_KEY}>baseline</span>
            <span style={FACT_VAL}>{baseline}</span>
          </div>
          {m?.maxAbsDeltaR2 != null && (
            <div style={FACT_ROW}>
              <span style={FACT_KEY}>max |Δr²|</span>
              <span style={FACT_VAL}>{m.maxAbsDeltaR2.toExponential(2)}</span>
            </div>
          )}
          {runDate != null && (
            <div style={FACT_ROW}>
              <span style={FACT_KEY}>run date</span>
              <span style={FACT_VAL}>{runDate}</span>
            </div>
          )}
        </div>
      </div>

      {/* Per-backend results table */}
      <div
        className="glass"
        style={{ padding: "var(--s6)", overflowX: "auto" }}
      >
        <h2
          style={{
            fontFamily: "var(--font-display)",
            fontWeight: 400,
            fontSize: "1.25rem",
            margin: "0 0 var(--s2)",
          }}
        >
          Measured medians across the suite
        </h2>
        <p
          style={{
            fontFamily: "var(--font-body)",
            fontSize: "0.86rem",
            color: "var(--ink-faint)",
            margin: "0 0 var(--s5)",
            maxWidth: "80ch",
          }}
        >
          One row per backend, sorted alphabetically — order implies nothing. Speedup is relative
          to the baseline ({baseline}&nbsp;=&nbsp;1.00×): a measured ratio, not a ranking.
        </p>
        <table
          style={{
            width: "100%",
            borderCollapse: "collapse",
            fontFamily: "var(--font-mono)",
            fontSize: "0.92rem",
          }}
        >
          <thead>
            <tr>
              <th style={TH_FIRST}>backend</th>
              <th style={TH_STYLE}>median solve (ms)</th>
              <th style={TH_STYLE}>median r²</th>
              <th style={TH_STYLE}>median speedup vs {baseline}</th>
              <th style={TH_STYLE}>cases run</th>
              <th style={TH_STYLE}>success</th>
            </tr>
          </thead>
          <tbody>
            {facts.map((f, idx) => {
              const isLast = idx === facts.length - 1;
              const rowStyle = isLast
                ? { ...TD_STYLE, borderBottom: "none" }
                : TD_STYLE;
              return (
                <tr key={f.id} style={{ cursor: "default" }}>
                  <td style={{ ...TD_FIRST, borderBottom: isLast ? "none" : "1px solid var(--hairline)" }}>
                    {f.id}
                  </td>
                  <td style={rowStyle}>{fmtMs(f.medMs)}</td>
                  <td style={rowStyle}>{fmtR2(f.medR2)}</td>
                  <td style={rowStyle}>{fmtSpeedup(f.medSpeedup)}</td>
                  <td style={rowStyle}>{f.casesRun}</td>
                  <td style={rowStyle}>{fmtPct(f.successRate)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Flow link → Evidence */}
      <a
        className="glass"
        href="#evidence"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--s4)",
          marginTop: "var(--s5)",
          padding: "var(--s5) var(--s6)",
          textDecoration: "none",
          color: "inherit",
        }}
        onClick={(e) => {
          e.preventDefault();
          window.location.hash = "#evidence";
        }}
      >
        <span>
          <span
            style={{
              fontFamily: "var(--font-display)",
              fontWeight: 400,
              fontSize: "1.15rem",
              color: "var(--ink)",
              display: "block",
            }}
          >
            All cases, side by side →
          </span>
          <span
            style={{
              fontFamily: "var(--font-body)",
              fontSize: "0.88rem",
              color: "var(--ink-dim)",
              marginTop: 2,
              display: "block",
            }}
          >
            Per-case fits, parameter recovery, convergence, conditioning — the full data.
          </span>
        </span>
        <span style={{ fontSize: "1.6rem", color: "var(--accent)" }}>→</span>
      </a>

      {/* Footer with optional-backend note */}
      {optionalAbsent.length > 0 && (
        <p
          style={{
            marginTop: "var(--s4)",
            fontFamily: "var(--font-mono)",
            fontSize: "0.74rem",
            color: "var(--ink-faint)",
          }}
        >
          Roster also declares an optional {optionalAbsent.join(", ")}{" "}
          backend{optionalAbsent.length > 1 ? "s" : ""} — not active in this run.
        </p>
      )}
    </>
  );
}
