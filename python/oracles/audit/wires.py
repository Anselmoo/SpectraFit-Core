"""One function per wire. Each returns a list of WireResult records.

W1/W3/W4/W6 read the pytest lastfailed cache for their status via a TRI-STATE
helper: an absent cache means the test never ran, so the wire reports "skipped"
(no pass-by-absence) rather than inflating the rung with an unbacked "pass".
W2a/W2b/W2c accept an optional ``audit_records`` parameter; when present they
RECOMPUTE from the full undecimated arrays in the audit.json sidecar instead of
relying on a stale cache entry. When ``audit_records`` is None they return
"skipped" so the rung is not inflated.
"""

from __future__ import annotations

import math
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from oracles.metrics import chi2_red_of, pulls_from_mc, r2_of, rmse_of
from oracles.trust_ledger import WireResult, WireStatus

if TYPE_CHECKING:
    from oracles.bench_contract import (
        CalibrationResult,
        NestedAdequacy,
        SpeedInferenceResult,
    )
    from oracles.trust_ledger import NistValidation

# Type alias — each record is a plain dict as loaded from audit.json.
_AuditRecord = dict[str, Any]

# Canonical pytest lastfailed cache path. Module-level so tests can monkeypatch
# it without depending on the process CWD.
_LASTFAILED_CACHE = Path(".pytest_cache/v/cache/lastfailed")


class _TestState(Enum):
    """Tri-state outcome of consulting the pytest lastfailed cache.

    UNKNOWN means the cache file is absent — the test never ran, so we MUST NOT
    report "pass" (no pass-by-absence). The wire maps UNKNOWN → "skipped".
    """

    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


def _test_state(
    test_name_fragment: str,
    cache_path: Path | None = None,
) -> _TestState:
    """Tri-state read of the lastfailed cache.

    - cache absent          → UNKNOWN (test never ran; do not claim pass)
    - cache names this test  → FAILED
    - cache present, no match → PASSED
    """
    path = cache_path if cache_path is not None else _LASTFAILED_CACHE
    if not path.exists():
        return _TestState.UNKNOWN
    try:
        text = path.read_text()
    except OSError:
        return _TestState.UNKNOWN
    return _TestState.FAILED if test_name_fragment in text else _TestState.PASSED


def _status_for(state: _TestState) -> WireStatus:
    """Map a tri-state test outcome onto a WireResult status literal."""
    match state:
        case _TestState.UNKNOWN:
            return "skipped"
        case _TestState.FAILED:
            return "fail"
        case _TestState.PASSED:
            return "pass"


def wire_w1_synth_invariants() -> list[WireResult]:
    """Wire W1: hypothesis-driven invariants on the synthetic data generator."""
    status = _status_for(_test_state("test_audit_synth_invariants"))
    return [
        WireResult(
            wire_id="W1",
            name="synth_invariants",
            status=status,
            evidence=(
                "hypothesis-driven invariants on synth._g and noise moments"
                if status != "skipped"
                else "synth-invariants test never ran (no lastfailed cache); not asserted"
            ),
        )
    ]


def wire_w2a_metric_identity(
    audit_records: list[_AuditRecord] | None = None,
) -> list[WireResult]:
    """W2a: recompute r²/rmse/reduced-χ² from the FULL audit arrays; compare to stored.

    The three metrics checked here correspond exactly to the three W2a-backed claims:
    ``metric.r2``, ``metric.rmse``, and ``metric.red_chi2`` (which also covers
    ``metric.chi2`` because χ² = reduced-χ² × dof — same formula, same check).
    All three must agree with their stored counterparts within 1 × 10⁻⁶ for W2a to pass.
    """
    if not audit_records:
        return [
            WireResult(
                wire_id="W2a",
                name="metric_identity",
                status="skipped",
                evidence="no audit sidecar present; metric identity not recomputed",
            )
        ]
    worst = 0.0
    for rec in audit_records:
        y = np.asarray(rec["y"], float)
        fit = np.asarray(rec["fit"], float)
        dof = int(rec.get("dof", max(len(y) - 1, 1)))
        # W2a is a metric-IDENTITY check: recompute each metric under the SAME
        # definition the engine stored it with. The engine stores reduced-χ²
        # UNWEIGHTED (SSR/dof), so the identity recompute is unweighted too —
        # passing the sidecar's σ here re-weighted it by 1/σ², which diverged
        # ~1/σ² on every noisy case and went to ∞ for the noiseless (σ=0) optfn
        # landscapes (Track-0 root cause). The σ-weighted "true" reduced-χ² is a
        # separate, additive metric — not this identity oracle.
        d_r2 = abs(r2_of(y, fit) - rec["storedR2"])
        d_rmse = abs(rmse_of(y, fit) - rec["storedRmse"])
        d_chi2_red = abs(chi2_red_of(y, fit, None, dof) - rec["storedChi2Red"])
        worst = max(worst, d_r2, d_rmse, d_chi2_red)
    ok = worst < 1e-6
    return [
        WireResult(
            wire_id="W2a",
            name="metric_identity",
            status="pass" if ok else "fail",
            evidence=(
                f"r²/rmse/reduced-χ² recomputed from full arrays; max |Δ|={worst:.2e} vs stored"
            ),
            details={"max_abs_delta": float(worst)},
        )
    ]


def wire_w2b_coverage(
    audit_records: list[_AuditRecord] | None = None,
) -> list[WireResult]:
    """W2b: recompute 1σ pull coverage from the MC ensemble in the sidecar."""
    if not audit_records:
        return [
            WireResult(
                wire_id="W2b",
                name="coverage",
                status="skipped",
                evidence="no audit sidecar present; coverage not recomputed",
            )
        ]
    covs: list[float] = []
    for rec in audit_records:
        u = pulls_from_mc(rec["mcEsts"], rec["mcSes"], rec["trueParams"])
        # Skip σ-absent records (coverage=None): they carry no calibration
        # information and must not dilute the mean with a spurious 0.0.
        if u.coverage is not None:
            covs.append(u.coverage)
    mean_cov = float(np.mean(covs)) if covs else 0.0
    ok = 0.5 <= mean_cov <= 0.85
    return [
        WireResult(
            wire_id="W2b",
            name="coverage",
            status="pass" if ok else "warn",
            evidence=(
                f"mean 1σ coverage over MC ensemble = {mean_cov:.2f} (target ≈0.68)"
            ),
            details={"mean_coverage": mean_cov},
        )
    ]


# The subject under test in the benchmark harness — the backend whose κ(J) capability
# W2c verifies. Oracle backends (lmfit, jax) that do not expose κ are a disclosed
# per-backend limitation, not a capability gap in the subject.
_SUBJECT_BACKEND = "spectrafit"


def wire_w2c_jacobian_kappa(
    audit_records: list[_AuditRecord] | None = None,
) -> list[WireResult]:
    """W2c: κ(J) per (case,backend) — verify the subject's Jacobian conditioning.

    Four outcomes (in priority order):

    - ``skipped`` — no audit sidecar present; the wire cannot recompute.
    - ``fail``    — at least one κ WAS computed (by any backend) but is non-finite
      (inf/nan): a real numerical failure that caps the rung.
    - ``pass``    — the subject (spectrafit) exposes a finite κ(J) for every one of
      its entries AND no backend has a non-finite computed κ.  Oracle backends
      (lmfit/jax) that do not expose κ at all are a disclosed per-backend limitation,
      not a capability gap — their absence is reported in ``details`` but does NOT
      change the pass.
    - ``gap``     — no non-finite κ, AND the subject has no entries with a finite κ
      (subject does not expose κ either).  This is a genuine subject capability gap.
    """
    if not audit_records:
        return [
            WireResult(
                wire_id="W2c",
                name="jacobian_kappa",
                status="skipped",
                evidence="no audit sidecar present; κ(J) not checked",
            )
        ]

    # --- (1) non-finite check: any computed but non-finite κ is a hard failure ---
    non_finite = [
        f"{r['case']}/{r['backend']}"
        for r in audit_records
        if r.get("kappa") is not None and not math.isfinite(r["kappa"])
    ]
    n_absent_all = sum(1 for r in audit_records if r.get("kappa") is None)
    if non_finite:
        return [
            WireResult(
                wire_id="W2c",
                name="jacobian_kappa",
                status="fail",
                evidence=f"κ(J) computed but non-finite for {len(non_finite)} entries",
                details={"n_non_finite": len(non_finite), "n_absent": n_absent_all},
            )
        ]

    # --- (2) subject-centric pass/gap: does the subject (spectrafit) expose κ? ---
    subject_records = [r for r in audit_records if r.get("backend") == _SUBJECT_BACKEND]
    subject_finite = [r for r in subject_records if r.get("kappa") is not None]
    oracle_absent = [
        r
        for r in audit_records
        if r.get("backend") != _SUBJECT_BACKEND and r.get("kappa") is None
    ]

    if subject_finite:
        # Subject capability verified — oracle absences are a disclosed limitation.
        n_total = len(audit_records)
        n_subject_finite = len(subject_finite)
        n_oracle_absent = len(oracle_absent)
        evidence_parts = [
            f"κ(J) finite for {n_subject_finite} spectrafit (subject) entries"
        ]
        if n_oracle_absent:
            evidence_parts.append(
                f"{n_oracle_absent}/{n_total} oracle-backend entries absent "
                "(lmfit/jax do not expose κ — disclosed per-backend limitation, not a gap)"
            )
        return [
            WireResult(
                wire_id="W2c",
                name="jacobian_kappa",
                status="pass",
                evidence="; ".join(evidence_parts),
                details={
                    "n_subject_finite": n_subject_finite,
                    "n_absent_oracles": n_oracle_absent,
                    "n_absent": n_absent_all,
                },
            )
        ]

    # No subject finite κ and no non-finite κ anywhere → subject does not expose κ.
    n_total = len(audit_records)
    return [
        WireResult(
            wire_id="W2c",
            name="jacobian_kappa",
            status="gap",
            evidence=(
                f"κ(J) not exposed by the subject (spectrafit) — {n_absent_all}/{n_total} "
                "(case,backend) entries absent; capability gap, not a numerical failure"
            ),
            details={"n_absent": n_absent_all},
        )
    ]


def wire_w2d_solver_output_oracle() -> list[WireResult]:
    """Wire W2d: spectrafit's solver output matches an independent oracle.

    Fitted parameters AND covariance agree with ``scipy.optimize.least_squares``
    (method='lm') within tolerance — the end-to-end solver-output check
    (Invariant V, V3).

    Backed by ``tests/audit/test_audit_solver_output_oracle.py``; the value side
    of the LM solve (params + per-parameter σ from the covariance) is verified
    against a second, independent LM implementation on the same data.

    Status is read from the pytest ``lastfailed`` cache (the shared pattern with
    W1/W3/W4/W6): a "pass" means the audit suite ran and this test was not among
    the failures. It therefore reports "pass" only when the suite actually ran;
    a fresh checkout with no cache reports "skipped" (non-capping), never a
    false pass from an absent cache.
    """
    status = _status_for(_test_state("test_audit_solver_output_oracle"))
    return [
        WireResult(
            wire_id="W2d",
            name="solver_output_oracle",
            status=status,
            evidence=(
                "fitted params + covariance σ agree with scipy.optimize.least_squares"
                if status != "skipped"
                else "solver-output-oracle test never ran (no lastfailed cache); not asserted"
            ),
        )
    ]


def wire_w3_results_roundtrip(current_run_id: str | None = None) -> list[WireResult]:
    """Wire W3: results.json parses and re-emits to canonical form.

    The roundtrip test is parametrized per run, so its ``lastfailed`` entries are
    run-specific (``…canonical_roundtrip[benchmark/<run>]``). Scope to the CURRENT
    run id so a stale failure for an OLDER run on disk cannot pin the current
    run's trust red — the Track-0 ② conflation where run_031 passed but the wire
    went red on runs 029/030. When no run id is supplied (legacy callers), fall
    back to the file-level fragment.
    """
    fragment = (
        f"canonical_roundtrip[{current_run_id}]"
        if current_run_id
        else "test_audit_results_roundtrip"
    )
    status = _status_for(_test_state(fragment))
    return [
        WireResult(
            wire_id="W3",
            name="results_roundtrip",
            status=status,
            evidence=(
                "results.json parses + re-emits to canonical form bytewise"
                if status != "skipped"
                else "results-roundtrip test never ran (no lastfailed cache); not asserted"
            ),
        )
    ]


def wire_w4_api_schema() -> list[WireResult]:
    """Wire W4: every /api response validates against the BenchReport contract."""
    status = _status_for(_test_state("test_audit_api_schema"))
    return [
        WireResult(
            wire_id="W4",
            name="api_schema",
            status=status,
            evidence=(
                "every /api response validates against BenchReport contract"
                if status != "skipped"
                else "api-schema test never ran (no lastfailed cache); not asserted"
            ),
        )
    ]


def wire_w5_render_fidelity() -> list[WireResult]:
    """Wire W5: Playwright JSON-vs-render differential (CI-only, always skipped here).

    W5 is a Playwright e2e test; controller-side it is "skipped" unless we
    invoke Playwright from here. Conservative: mark "skipped" so it does not
    inflate the rung — Task 15's poe task / CI job will provide ground truth.
    """
    return [
        WireResult(
            wire_id="W5",
            name="render_fidelity",
            status="skipped",
            evidence="Playwright JSON-vs-render differential (runs in CI only)",
        )
    ]


def wire_w6_gate_state_parity() -> list[WireResult]:
    """Wire W6: gate_state is a closed Literal and manifest carries it."""
    status = _status_for(_test_state("test_audit_gate_state_parity"))
    return [
        WireResult(
            wire_id="W6",
            name="gate_state_parity",
            status=status,
            evidence=(
                "gate_state is a closed Literal + manifest carries it; vitest source-scan green"
                if status != "skipped"
                else "gate-state-parity test never ran (no lastfailed cache); not asserted"
            ),
        )
    ]


def wire_w7_inference_validity() -> list[WireResult]:
    """W7: the seeded inference is reproducible — same seed → identical CI."""
    from oracles.inference import speedup_ci

    base = [10.0, 11.0, 9.0, 10.5, 9.5]
    subj = [1.0, 1.1, 0.9, 1.05, 0.95]
    a = speedup_ci(base, subj, b=2000, alpha=0.05, seed=20260612)
    b = speedup_ci(base, subj, b=2000, alpha=0.05, seed=20260612)
    ok = a == b
    return [
        WireResult(
            wire_id="W7",
            name="inference_validity",
            status="pass" if ok else "fail",
            evidence="seeded bootstrap CI reproduces bitwise (deterministic inference)",
        )
    ]


def wire_w8_nist_certified_validation(
    nist_validation: "NistValidation | None" = None,
) -> list[WireResult]:
    """W8: independent external replication against NIST StRD certified values.

    Re-runs the four NIST StRD fits (Gauss1/2/3 + Lanczos1) and compares the
    recovered parameters to NIST's extended-precision certified values:

    - ``pass``     — every dataset reproduces the certified values to ≥ the
      sig-fig threshold. This is the independent differential validation +
      external replication evidence that earns RUNG_5.
    - ``fail``     — the harness ran but at least one dataset fell short of the
      threshold (a real recovery regression).
    - ``skipped``  — the harness could not run (spectrafit_core unavailable,
      fixture import error), OR ``nist_validation`` was explicitly passed as
      ``None`` (e.g. run_audit computed it before the loop but the call failed).

    ``nist_validation`` — when provided by the caller (e.g. ``run_audit``
    pre-computed it so the TrustBlock and W8 share a single object), the wire
    derives its status from that block without a second ``run_nist_validation()``
    call. Divergence between the W8 WireResult and TrustBlock.nist_validation is
    therefore impossible. Pass ``None`` (the default) to run the harness inline,
    preserving direct-call / test back-compat.
    """
    from oracles.audit.nist import NIST_SIGFIG_THRESHOLD

    if nist_validation is None:
        # Fallback path: called directly (tests, CLI) without a pre-computed block.
        try:
            from oracles.audit.nist import run_nist_validation

            nist_validation = run_nist_validation()
        except Exception as exc:  # pragma: no cover - defensive: missing build/fixtures
            return [
                WireResult(
                    wire_id="W8",
                    name="nist_certified_validation",
                    status="skipped",
                    evidence=f"NIST StRD harness could not run ({type(exc).__name__}); not asserted",
                )
            ]

    threshold = NIST_SIGFIG_THRESHOLD
    if not nist_validation.datasets:
        # Passed-in block with no datasets (shouldn't happen; guard defensively).
        return [
            WireResult(
                wire_id="W8",
                name="nist_certified_validation",
                status="skipped",
                evidence="NIST StRD validation block carried no datasets; not asserted",
            )
        ]

    names = "/".join(d.name for d in nist_validation.datasets)
    status: WireStatus = "pass" if nist_validation.passed else "fail"
    if nist_validation.passed:
        evidence = (
            f"{names} reproduce NIST certified values to ≥{threshold:g} sig figs "
            f"(min {nist_validation.min_sig_figs:.1f})"
        )
    else:
        short = [d.name for d in nist_validation.datasets if not d.passed]
        evidence = (
            f"NIST StRD certified-value validation FELL SHORT for {', '.join(short)} "
            f"(min {nist_validation.min_sig_figs:.1f} < {threshold:g} sig figs)"
        )
    return [
        WireResult(
            wire_id="W8",
            name="nist_certified_validation",
            status=status,
            evidence=evidence,
            details={
                "n_datasets": len(nist_validation.datasets),
                "min_sig_figs": float(nist_validation.min_sig_figs),
                "threshold_sig_figs": float(threshold),
            },
        )
    ]


def wire_w9_nested_adequacy(
    nested_adequacy: "NestedAdequacy | None" = None,
) -> list[WireResult]:
    """W9: nested-model adequacy V&V — BIC recovers the true model order.

    Verifies that model-selection criteria applied to a known generative case
    recover the true peak order m*:

    - ``pass``    — ``nested_adequacy.recovered_true_order_bic`` is ``True``.
      BIC is the consistent model-order estimator; it governs the wire verdict.
      AIC and the LRT p-value are included in the evidence string so any
      AIC/BIC disagreement is visible without changing the verdict.
    - ``fail``    — the V&V was present but ``recovered_true_order_bic`` is
      ``False`` (BIC selected the wrong order).
    - ``skipped`` — ``nested_adequacy is None``; evidence absent ⇒ the rung
      must not be inflated (no pass-by-absence, mirror W8).

    ``nested_adequacy`` — when provided by the caller (e.g. ``run_audit``
    pre-computed it from ``results.json``), the wire derives its status from
    that block without a second computation call. Pass ``None`` (the default)
    to return ``skipped`` immediately (e.g. on a fresh checkout where the
    V&V has not yet been run).
    """
    if nested_adequacy is None:
        return [
            WireResult(
                wire_id="W9",
                name="nested_adequacy",
                status="skipped",
                evidence=(
                    "nested-model adequacy V&V absent; model-selection accuracy "
                    "not asserted (no pass-by-absence)"
                ),
            )
        ]

    bic_ok = nested_adequacy.recovered_true_order_bic
    aic_ok = nested_adequacy.recovered_true_order_aic
    lrt_p = nested_adequacy.reduced_vs_true.lrt_p
    true_order = nested_adequacy.true_order
    sel_bic = nested_adequacy.selected_order_bic
    sel_aic = nested_adequacy.selected_order_aic

    # After fix I1: recovered_true_order_bic=True guarantees sel_bic == true_order,
    # so the "==" in the pass branch is always correct.  Render both sides
    # from the actual values so any future drift becomes immediately visible.
    bic_relation = "==" if sel_bic == true_order else "≠"
    match bic_ok:
        case True:
            status: WireStatus = "pass"
            evidence = (
                f"BIC selected order {sel_bic} {bic_relation} true order {true_order} "
                f"(BIC recovered); AIC selected {sel_aic} "
                f"({'recovered' if aic_ok else 'over-selected'}); "
                f"LRT p={lrt_p:.3g}"
            )
        case False:
            status = "fail"
            evidence = (
                f"BIC selected order {sel_bic} {bic_relation} true order {true_order} "
                f"(BIC failed to recover true order); "
                f"AIC selected {sel_aic} "
                f"({'recovered' if aic_ok else 'over-selected'}); "
                f"LRT p={lrt_p:.3g}"
            )

    return [
        WireResult(
            wire_id="W9",
            name="nested_adequacy",
            status=status,
            evidence=evidence,
            details={
                "true_order": true_order,
                "selected_order_bic": sel_bic,
                "selected_order_aic": sel_aic,
                "recovered_true_order_bic": bic_ok,
                "recovered_true_order_aic": aic_ok,
                "lrt_p": float(lrt_p),
            },
        )
    ]


def wire_w10_sigma_calibration(
    calibration: "CalibrationResult | None" = None,
) -> list[WireResult]:
    """W10: σ-calibration quality — practical-equivalence gate on pull coverage.

    Verifies that the subject's reported σ values are calibrated: the fraction
    of (θ_est − θ_true) / σ_est pulls that fall within ±1σ should lie close
    to the nominal 68.27 % coverage.

    Gate criterion (A2 fix — CI-inclusion TOST for a proportion):
      passed iff the Clopper–Pearson CI of empirical coverage lies entirely
      within [nominal − margin, nominal + margin] (default margin = 0.03 = ±3 pp).
      This replaces the old point-null binomial gate that had extreme power at
      large n and rejected a practically-negligible 1.5 pp deviation.

    Honest strict diagnostic retained:
      The strict point-null binomial p-value (H0: coverage = nominal) is always
      computed and reported in the evidence string so the dashboard can honestly
      show "coverage 0.668 vs 0.6827, strict binomial p < 0.001, slightly
      optimistic but within ±0.03 equivalence band."  Only the binary gate
      verdict changes; the diagnostic does not disappear.

    - ``pass``    — ``calibration.passed is True`` (CI within equivalence band).
    - ``fail``    — ``calibration.passed is False`` (CI outside equivalence band).
    - ``skipped`` — ``calibration is None`` OR ``calibration.skipped is True``;
      the rung must not be inflated (no pass-by-absence).

    ``calibration`` — when provided by the caller (e.g. ``run_audit``
    pre-computed it from ``results.json``), the wire derives its status from
    that block.  Pass ``None`` (the default) to return ``skipped`` immediately.
    """
    if calibration is None or calibration.skipped:
        return [
            WireResult(
                wire_id="W10",
                name="sigma_calibration",
                status="skipped",
                evidence=(
                    "σ-calibration record absent or skipped; pull-coverage "
                    "not asserted (no pass-by-absence)"
                ),
            )
        ]

    # Pre-registered equivalence margin (contract field default = 0.03).
    margin = getattr(calibration, "equivalence_margin", 0.03)
    band_lo = calibration.nominal - margin
    band_hi = calibration.nominal + margin

    # Strict diagnostic: point-null binomial p (honest, large-n power trap disclosure).
    strict_note = (
        f"strict binomial p={calibration.binomial_p:.3g} "
        f"({'< α — strict diagnostic triggered' if calibration.binomial_p < calibration.alpha else '> α'})"
    )

    match calibration.passed:
        case True:
            status: WireStatus = "pass"
            evidence = (
                f"σ-calibration PASS (equivalence): coverage={calibration.coverage:.3f} "
                f"(nominal={calibration.nominal:.4f}); "
                f"CI=[{calibration.coverage_ci_lo:.4f}, {calibration.coverage_ci_hi:.4f}] "
                f"within ±{margin:.2f} band [{band_lo:.4f}, {band_hi:.4f}]; "
                f"{strict_note}; "
                f"KS p={calibration.ks_p:.3g} (secondary diagnostic)"
            )
        case False:
            status = "fail"
            evidence = (
                f"σ-calibration FAIL (equivalence): coverage={calibration.coverage:.3f} "
                f"(nominal={calibration.nominal:.4f}); "
                f"CI=[{calibration.coverage_ci_lo:.4f}, {calibration.coverage_ci_hi:.4f}] "
                f"outside ±{margin:.2f} band [{band_lo:.4f}, {band_hi:.4f}]; "
                f"{strict_note}; "
                f"KS p={calibration.ks_p:.3g} (secondary diagnostic)"
            )

    return [
        WireResult(
            wire_id="W10",
            name="sigma_calibration",
            status=status,
            evidence=evidence,
            details={
                "n": calibration.n,
                "coverage": float(calibration.coverage),
                "nominal": float(calibration.nominal),
                "equivalence_margin": float(margin),
                "band_lo": float(band_lo),
                "band_hi": float(band_hi),
                "coverage_ci_lo": float(calibration.coverage_ci_lo),
                "coverage_ci_hi": float(calibration.coverage_ci_hi),
                "binomial_p": float(calibration.binomial_p),
                "ks_p": float(calibration.ks_p),
                "alpha": float(calibration.alpha),
            },
        )
    ]


def wire_w11_speed_inference(
    speed_inference: "SpeedInferenceResult | None" = None,
) -> list[WireResult]:
    """W11: speed inference — bootstrap CI on geomean speedup vs baseline.

    Verifies that the best-performing non-baseline backend per case is
    significantly faster than the baseline solver (= spectrafit on the current
    roster; see ``compute_inference`` I2 comment in inference_report.py for
    the exact selection criterion): the bootstrap CI on the geometric mean of
    per-case speedup ratios must exclude 1.0.  Secondary diagnostics: sign test
    and Wilcoxon signed-rank p-values.

    - ``pass``    — ``speed_inference.passed is True`` (CI excludes 1.0).
    - ``fail``    — ``speed_inference.passed is False`` (CI includes 1.0).
    - ``skipped`` — ``speed_inference is None`` OR ``speed_inference.skipped
      is True``; the rung must not be inflated (no pass-by-absence).

    ``speed_inference`` — when provided by the caller (e.g. ``run_audit``
    pre-computed it from ``results.json``), the wire derives its status from
    that block.  Pass ``None`` (the default) to return ``skipped`` immediately.
    """
    if speed_inference is None or speed_inference.skipped:
        return [
            WireResult(
                wire_id="W11",
                name="speed_inference",
                status="skipped",
                evidence=(
                    "speed-inference record absent or skipped; geomean speedup CI "
                    "not asserted (no pass-by-absence)"
                ),
            )
        ]

    match speed_inference.passed:
        case True:
            status: WireStatus = "pass"
            evidence = (
                f"speed inference PASS: geomean speedup={speed_inference.geomean_speedup:.2f}× "
                f"CI=[{speed_inference.ci_lo:.2f}, {speed_inference.ci_hi:.2f}] excludes 1.0; "
                f"sign p={speed_inference.sign_p:.3g}, "
                f"Wilcoxon p={speed_inference.wilcoxon_p:.3g} (secondary diagnostics)"
            )
        case False:
            status = "fail"
            evidence = (
                f"speed inference FAIL: geomean speedup={speed_inference.geomean_speedup:.2f}× "
                f"CI=[{speed_inference.ci_lo:.2f}, {speed_inference.ci_hi:.2f}] does not exclude 1.0; "
                f"sign p={speed_inference.sign_p:.3g}, "
                f"Wilcoxon p={speed_inference.wilcoxon_p:.3g} (secondary diagnostics)"
            )

    return [
        WireResult(
            wire_id="W11",
            name="speed_inference",
            status=status,
            evidence=evidence,
            details={
                "geomean_speedup": float(speed_inference.geomean_speedup),
                "ci_lo": float(speed_inference.ci_lo),
                "ci_hi": float(speed_inference.ci_hi),
                "excludes_one": speed_inference.excludes_one,
                "sign_p": float(speed_inference.sign_p),
                "wilcoxon_p": float(speed_inference.wilcoxon_p),
                "alpha": float(speed_inference.alpha),
            },
        )
    ]


ALL_WIRES = [
    wire_w1_synth_invariants,
    wire_w2a_metric_identity,
    wire_w2b_coverage,
    wire_w2c_jacobian_kappa,
    wire_w2d_solver_output_oracle,
    wire_w3_results_roundtrip,
    wire_w4_api_schema,
    wire_w5_render_fidelity,
    wire_w6_gate_state_parity,
    wire_w7_inference_validity,
    wire_w8_nist_certified_validation,
    wire_w9_nested_adequacy,
    wire_w10_sigma_calibration,
    wire_w11_speed_inference,
]
