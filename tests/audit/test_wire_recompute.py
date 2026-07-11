"""TDD tests for W2a/W2b/W2c live-recompute from audit.json sidecar.

These tests use inline fixtures only — no benchmark runs, no disk I/O
other than a tiny tmp_path. All must complete in well under 10 seconds.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pytest

import oracles.audit.wires as wires_mod
from oracles.metrics import chi2_red_of, r2_of, rmse_of
from oracles.audit.wires import (
    wire_w1_synth_invariants,
    wire_w2a_metric_identity,
    wire_w2b_coverage,
    wire_w2c_jacobian_kappa,
    wire_w3_results_roundtrip,
    wire_w4_api_schema,
    wire_w6_gate_state_parity,
)


def _record(y, fit, **over):
    y = np.asarray(y, float)
    fit = np.asarray(fit, float)
    dof = max(len(y) - 2, 1)
    rec = {
        "case": "T-1",
        "backend": "spectrafit",
        "y": y.tolist(),
        "fit": fit.tolist(),
        "sigma": 1.0,
        "dof": dof,
        "storedR2": float(r2_of(y, fit)),
        # Compute storedChi2Red from y/fit/sigma/dof so it matches the
        # recomputed value — a hardcoded 1.0 was a dummy that would cause
        # W2a to flag a spurious deviation once chi2_red checking was added.
        "storedChi2Red": float(chi2_red_of(y, fit, sigma=None, dof=dof)),
        "storedRmse": float(rmse_of(y, fit)),
        "kappa": 12.5,
        "mcEsts": [{"a": 1.0}, {"a": 1.1}, {"a": 0.9}],
        "mcSes": [{"a": 0.2}, {"a": 0.2}, {"a": 0.2}],
        "trueParams": {"a": 1.0},
    }
    rec.update(over)
    return rec


# ---------------------------------------------------------------------------
# W2a — metric identity
# ---------------------------------------------------------------------------

def test_w2a_passes_when_stored_matches_recompute():
    y = [1.0, 2.0, 3.0, 4.0]
    fit = [1.1, 1.9, 3.05, 3.95]
    out = wire_w2a_metric_identity(audit_records=[_record(y, fit)])
    assert out[0].status == "pass"


def test_w2a_fails_when_stored_metric_diverges():
    y = [1.0, 2.0, 3.0, 4.0]
    fit = [1.1, 1.9, 3.05, 3.95]
    out = wire_w2a_metric_identity(audit_records=[_record(y, fit, storedR2=0.0)])
    assert out[0].status == "fail"


def test_w2a_skipped_when_no_records():
    out = wire_w2a_metric_identity(audit_records=None)
    assert out[0].status == "skipped"


def test_w2a_fails_when_stored_chi2_red_diverges():
    """W2a must catch a bogus storedChi2Red — a deviation the wire did NOT check
    before fix S1-F1 (A-D review).  The `_MetricChi2` / `_MetricRedChi2` claims
    assert recomputation; the wire must honour that assertion.

    Construct a record whose y/fit imply a reduced-χ² of ~0.0125 (sigma=1, dof=2)
    but whose storedChi2Red is 999.0 — a gross error that must be caught.
    """
    y = [1.0, 2.0, 3.0, 4.0]
    fit = [1.1, 1.9, 3.05, 3.95]
    # Override storedChi2Red with a grossly wrong value
    out = wire_w2a_metric_identity(
        audit_records=[_record(y, fit, storedChi2Red=999.0)]
    )
    assert out[0].status == "fail", (
        "W2a must fail when storedChi2Red deviates from recomputed value; "
        "currently the chi2_red check does not run (S1-F1)"
    )


def test_w2a_passes_with_realistic_nonunit_sigma():
    """Production sidecars carry the REAL scalar σ (e.g. 0.5), not 1.0.

    The engine stores reduced-χ² UNWEIGHTED (SSR/dof).  W2a is a metric-IDENTITY
    check, so it must recompute under the engine's own (unweighted) definition —
    NOT re-weight by σ.  With σ≠1 the old wire wove a σ-weighted recompute that
    diverged ~1/σ² from the unweighted stored value (Track-0 root cause: every
    noisy case failed W2a).  The σ=1.0 in `_record` masked this for years.
    """
    y = [1.0, 2.0, 3.0, 4.0]
    fit = [1.1, 1.9, 3.05, 3.95]
    out = wire_w2a_metric_identity(audit_records=[_record(y, fit, sigma=0.5)])
    assert out[0].status == "pass", (
        "W2a must recompute reduced-χ² under the stored (unweighted) definition, "
        "independent of the sidecar's σ"
    )


def test_w2a_no_inf_when_sigma_zero_noiseless():
    """Noiseless cases (the 20 optfn `OF-*` landscapes) carry σ=0.

    A σ-weighted recompute does 1/0² → inf → `max|Δ|=inf` (the live `run_031`
    symptom that capped the rung at 2).  The unweighted identity recompute must
    stay finite and pass.
    """
    y = [1.0, 2.0, 3.0, 4.0]
    fit = [1.1, 1.9, 3.05, 3.95]
    out = wire_w2a_metric_identity(audit_records=[_record(y, fit, sigma=0.0)])
    assert out[0].status == "pass", "σ=0 must not yield inf in the W2a identity recompute"
    delta = out[0].details["max_abs_delta"]
    assert delta is not None and math.isfinite(float(delta))


# ---------------------------------------------------------------------------
# W2c — jacobian kappa
# ---------------------------------------------------------------------------

def test_w2c_passes_when_kappa_finite_everywhere():
    out = wire_w2c_jacobian_kappa(audit_records=[_record([1, 2], [1, 2], kappa=10.0)])
    assert out[0].status == "pass"


def test_w2c_gap_when_kappa_absent():
    """κ(J) not exposed by the backend → capability gap (not a failure).

    Track A Wave 2: a missing κ is a disclosed CAPABILITY gap, so W2c returns
    `gap`. `fail` is reserved for a κ that WAS computed but is non-finite.
    """
    out = wire_w2c_jacobian_kappa(audit_records=[_record([1, 2], [1, 2], kappa=None)])
    assert out[0].status == "gap"


def test_w2c_fails_when_kappa_non_finite():
    out = wire_w2c_jacobian_kappa(
        audit_records=[_record([1, 2], [1, 2], kappa=float("inf"))]
    )
    assert out[0].status == "fail"


def test_w2c_skipped_when_no_records():
    out = wire_w2c_jacobian_kappa(audit_records=None)
    assert out[0].status == "skipped"


# ---------------------------------------------------------------------------
# W2b — coverage
# ---------------------------------------------------------------------------

def test_w2b_passes_with_reasonable_coverage():
    out = wire_w2b_coverage(audit_records=[_record([1, 2], [1, 2])])
    assert out[0].status in {"pass", "warn"}


def test_w2b_skipped_when_no_records():
    out = wire_w2b_coverage(audit_records=None)
    assert out[0].status == "skipped"


# ---------------------------------------------------------------------------
# Runner integration — sidecar consumed by run_audit
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# W1/W3/W4/W6 — no pass-by-absence (cache file missing ⇒ skipped, not pass)
# ---------------------------------------------------------------------------


@pytest.fixture
def _absent_lastfailed(tmp_path, monkeypatch):
    """Point the wires at a lastfailed cache path that does NOT exist."""
    missing = tmp_path / ".pytest_cache" / "v" / "cache" / "lastfailed"
    monkeypatch.setattr(wires_mod, "_LASTFAILED_CACHE", missing, raising=False)
    return missing


@pytest.fixture
def _failed_lastfailed(tmp_path, monkeypatch):
    """A lastfailed cache that exists and names the given test."""
    cache = tmp_path / "lastfailed"
    cache.write_text('{"tests/audit/x.py::test_audit_synth_invariants": true}')
    monkeypatch.setattr(wires_mod, "_LASTFAILED_CACHE", cache, raising=False)
    return cache


@pytest.fixture
def _passing_lastfailed(tmp_path, monkeypatch):
    """A lastfailed cache that exists but names no W-wire test ⇒ pass."""
    cache = tmp_path / "lastfailed"
    cache.write_text('{"tests/unrelated.py::test_other": true}')
    monkeypatch.setattr(wires_mod, "_LASTFAILED_CACHE", cache, raising=False)
    return cache


@pytest.mark.parametrize(
    "wire_fn",
    [
        wire_w1_synth_invariants,
        wire_w3_results_roundtrip,
        wire_w4_api_schema,
        wire_w6_gate_state_parity,
    ],
)
def test_wire_skipped_when_cache_absent(wire_fn, _absent_lastfailed):
    """No pass-by-absence: when the cache never ran, the wire is 'skipped'."""
    assert wire_fn()[0].status == "skipped"


def test_w1_skipped_when_cache_absent(_absent_lastfailed):
    assert wire_w1_synth_invariants()[0].status == "skipped"


def test_w1_fail_when_cache_records_failure(_failed_lastfailed):
    assert wire_w1_synth_invariants()[0].status == "fail"


def test_w1_pass_when_cache_present_and_clean(_passing_lastfailed):
    assert wire_w1_synth_invariants()[0].status == "pass"


# ---------------------------------------------------------------------------
# W3 — must reflect the CURRENT run, not stale cross-run pytest cache (Track-0 ②)
# ---------------------------------------------------------------------------

_ROUNDTRIP_NODE = (
    "tests/audit/test_audit_results_roundtrip.py::"
    "test_results_json_canonical_roundtrip[benchmark/{run}]"
)


def test_w3_ignores_other_runs_roundtrip_failures(tmp_path, monkeypatch):
    """A stale roundtrip failure for an OLDER run must not pin the current run red.

    The roundtrip test is parametrized per run; on live run_031 the wire went
    red only because old runs 029/030 were in the lastfailed cache while
    run_031 itself passed. Scoping to the current run id fixes the conflation.
    """
    cache = tmp_path / "lastfailed"
    cache.write_text(json.dumps({_ROUNDTRIP_NODE.format(run="2026-06-18_run_029"): True}))
    monkeypatch.setattr(wires_mod, "_LASTFAILED_CACHE", cache, raising=False)
    out = wire_w3_results_roundtrip(current_run_id="benchmark/2026-06-18_run_031")
    assert out[0].status == "pass"


def test_w3_fails_when_current_run_roundtrip_failed(tmp_path, monkeypatch):
    """If the CURRENT run's own roundtrip failed, W3 must still fail."""
    cache = tmp_path / "lastfailed"
    cache.write_text(json.dumps({_ROUNDTRIP_NODE.format(run="2026-06-18_run_031"): True}))
    monkeypatch.setattr(wires_mod, "_LASTFAILED_CACHE", cache, raising=False)
    out = wire_w3_results_roundtrip(current_run_id="benchmark/2026-06-18_run_031")
    assert out[0].status == "fail"


def test_run_audit_consumes_sidecar(tmp_path: Path, no_runtime_l3):
    from oracles.audit.runner import run_audit

    y = [1.0, 2.0, 3.0, 4.0]
    fit = [1.05, 2.02, 2.98, 3.97]
    recs = [_record(y, fit)]
    (tmp_path / "audit.json").write_text(json.dumps(recs))
    (tmp_path / "results.json").write_text(json.dumps({"schemaVersion": "1.4"}))
    ledger = run_audit(tmp_path)
    w2a = next(w for w in ledger.block.wires if w.wire_id == "W2a")
    assert w2a.status == "pass"
    assert (tmp_path / "trust.json").exists()


def test_run_audit_output_revalidates_as_benchreport(tmp_path: Path, no_runtime_l3):
    """Regression: the inlined trust block must use the camelCase alias
    `trustBlock` and re-validate through BenchReport. A snake_case
    `trust_block` sibling was an extra_forbidden key that 500'd /api/report."""
    from oracles.audit.runner import run_audit
    from oracles.synth import build_report
    from oracles.bench_contract import BenchReport

    rep = build_report()
    (tmp_path / "results.json").write_text(rep.model_dump_json(by_alias=True))
    (tmp_path / "audit.json").write_text(
        json.dumps([_record([1.0, 2.0, 3.0], [1.05, 1.98, 3.02])])
    )
    run_audit(tmp_path)
    raw = json.loads((tmp_path / "results.json").read_text())
    assert "trust_block" not in raw, "snake_case sibling must not exist"
    assert raw.get("trustBlock") is not None
    BenchReport.model_validate(raw)  # must not raise
