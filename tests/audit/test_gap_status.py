"""Track A Wave 2 — `gap` WireStatus: a disclosed capability gap is NOT a failure.

W2c (κ(J)) returns `fail` only when a κ WAS computed but is non-finite. When the
backend simply does not expose κ at all (the 337-entry capability gap), it returns
`gap`. A `gap` (like `skipped`) must NOT cap the credibility rung — only a genuine
`fail` caps it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import get_args

import oracles.audit.runner as runner_mod
from oracles.audit.claims import CLAIM_REGISTRY, audited_count
from oracles.audit.runner import _compute_rung, run_audit
from oracles.audit.wires import wire_w2c_jacobian_kappa
from oracles.trust_ledger import CredibilityRung, WireResult, WireStatus


# ---------------------------------------------------------------------------
# Step 1 — `gap` is a valid WireStatus
# ---------------------------------------------------------------------------


def test_gap_is_a_valid_wire_status():
    assert "gap" in get_args(WireStatus)
    # And it remains constructible on a WireResult.
    wr = WireResult(
        wire_id="W2c", name="jacobian_kappa", status="gap", evidence="κ(J) not exposed"
    )
    assert wr.status == "gap"


def test_all_four_legacy_statuses_still_valid():
    for s in ("pass", "warn", "fail", "skipped"):
        assert s in get_args(WireStatus)


# ---------------------------------------------------------------------------
# Step 3 — the CredibilityRung enum contract is explicit (RUNG_1..RUNG_5)
# ---------------------------------------------------------------------------


def test_credibility_rung_enum_values_are_1_through_5():
    assert [r.value for r in CredibilityRung] == [1, 2, 3, 4, 5]
    assert CredibilityRung.RUNG_1 == 1
    assert CredibilityRung.RUNG_5 == 5


# ---------------------------------------------------------------------------
# Step 2 — W2c distinguishes a capability GAP from a numerical FAILURE
# ---------------------------------------------------------------------------


def _rec(kappa, case="T-1", backend="spectrafit"):
    return {"case": case, "backend": backend, "kappa": kappa}


def test_w2c_gap_when_kappa_absent_everywhere():
    """All κ absent (backend does not expose it) → capability gap, not failure."""
    out = wire_w2c_jacobian_kappa(audit_records=[_rec(None), _rec(None, case="T-2")])
    assert out[0].status == "gap"


def test_w2c_gap_when_subject_kappa_absent_and_oracles_also_absent():
    """Subject (spectrafit) has no κ AND oracle backends also absent → gap (subject unverified)."""
    records = [
        _rec(None, case="T-1", backend="spectrafit"),
        _rec(None, case="T-1", backend="lmfit"),
        _rec(None, case="T-1", backend="jax"),
    ]
    out = wire_w2c_jacobian_kappa(audit_records=records)
    assert out[0].status == "gap"


def test_w2c_pass_when_subject_has_finite_kappa_but_oracle_backends_absent():
    """Subject (spectrafit) exposes finite κ; lmfit/jax absent → PASS (oracle absence is disclosed, not a gap).

    This is the key semantic change: W2c passes when the subject's κ(J) capability is
    verified, even if oracle backends (lmfit/jax) do not expose κ.  The prior code
    returned 'gap' for ANY absent entry; it now keys off the subject's status.
    """
    records = [
        _rec(42.0, case="T-1", backend="spectrafit"),
        _rec(15.0, case="T-2", backend="spectrafit"),
        _rec(None, case="T-1", backend="lmfit"),
        _rec(None, case="T-2", backend="lmfit"),
        _rec(None, case="T-1", backend="jax"),
    ]
    out = wire_w2c_jacobian_kappa(audit_records=records)
    assert out[0].status == "pass", (
        f"expected 'pass' (subject has finite κ, oracle absences are disclosed); got {out[0].status!r}. "
        "W2c must pass when spectrafit (the subject) exposes κ(J); lmfit/jax absence is a "
        "per-backend oracle limitation, not a capability gap in the subject under test."
    )
    # Absence count still disclosed in details.
    assert out[0].details is not None
    assert out[0].details.get("n_absent_oracles", 0) == 3


def test_w2c_fail_when_subject_kappa_non_finite():
    """Subject κ computed but non-finite → real failure regardless of oracle state."""
    records = [
        _rec(float("inf"), case="T-1", backend="spectrafit"),
        _rec(None, case="T-1", backend="lmfit"),
    ]
    out = wire_w2c_jacobian_kappa(audit_records=records)
    assert out[0].status == "fail"


def test_w2c_fail_when_a_computed_kappa_is_non_finite():
    """A κ that WAS computed but is non-finite (inf/nan) is a real failure."""
    out = wire_w2c_jacobian_kappa(
        audit_records=[_rec(10.0), _rec(float("inf"), case="T-2")]
    )
    assert out[0].status == "fail"


def test_w2c_pass_when_all_kappa_finite():
    out = wire_w2c_jacobian_kappa(audit_records=[_rec(10.0), _rec(12.5, case="T-2")])
    assert out[0].status == "pass"


def test_w2c_skipped_when_no_records():
    out = wire_w2c_jacobian_kappa(audit_records=None)
    assert out[0].status == "skipped"


# ---------------------------------------------------------------------------
# Step 3 — `gap` does NOT cap the rung; a real `fail` still caps it
# ---------------------------------------------------------------------------


def _wires(statuses: dict[str, WireStatus]) -> list[WireResult]:
    return [
        WireResult(wire_id=k, name=k, status=v, evidence="stub")
        for k, v in statuses.items()
    ]


def test_gap_does_not_cap_the_rung():
    """7 passing wires + W2c=gap → rung rises to 4 (gap does not cap at 2)."""
    statuses: dict[str, WireStatus] = {
        "W1": "pass",
        "W2a": "pass",
        "W2b": "pass",
        "W2c": "gap",
        "W3": "pass",
        "W4": "pass",
        "W5": "skipped",
        "W6": "pass",
        "W7": "pass",
    }
    rung = _compute_rung(_wires(statuses))
    assert rung == CredibilityRung.RUNG_4
    assert rung > CredibilityRung.RUNG_2


def test_real_fail_still_caps_the_rung():
    statuses: dict[str, WireStatus] = {
        "W1": "pass",
        "W2a": "fail",
        "W2b": "pass",
        "W2c": "gap",
        "W3": "pass",
        "W4": "pass",
        "W5": "skipped",
        "W6": "pass",
        "W7": "pass",
    }
    assert _compute_rung(_wires(statuses)) == CredibilityRung.RUNG_2


# ---------------------------------------------------------------------------
# Step 4 — claim ledger: a gap-backed claim is NOT audited (pass-only count)
# ---------------------------------------------------------------------------


def test_audited_count_excludes_gap_backed_claims():
    total = len(CLAIM_REGISTRY)
    n_w2c = sum(1 for c in CLAIM_REGISTRY.values() if c.wire_id == "W2c")
    assert n_w2c >= 1

    wire_status = {c.wire_id: "pass" for c in CLAIM_REGISTRY.values()}
    wire_status["W2c"] = "gap"
    assert audited_count(wire_status) == total - n_w2c
    assert audited_count(wire_status) < total


# ---------------------------------------------------------------------------
# Runner integration — a gap wire lifts the rung but stays un-audited
# ---------------------------------------------------------------------------


def test_runner_gap_lifts_rung_and_keeps_claim_unaudited(
    tmp_path: Path, monkeypatch, no_runtime_l3
):
    real_ids = ["W1", "W2a", "W2b", "W2c", "W2d", "W3", "W4", "W6", "W7"]

    def _make(wid: str):
        status = "gap" if wid == "W2c" else "pass"

        def _fn() -> list[WireResult]:
            return [WireResult(wire_id=wid, name=wid, status=status, evidence="stub")]

        return _fn

    monkeypatch.setattr(runner_mod, "ALL_WIRES", [_make(w) for w in real_ids])
    (tmp_path / "results.json").write_text(json.dumps({"x": 1}))

    block = run_audit(tmp_path).block
    # This stub omits W2c (gap) and W8 (absent), so claims backed by either wire
    # stay un-audited — the honest count subtracts both.
    n_unaudited = sum(1 for c in CLAIM_REGISTRY.values() if c.wire_id in {"W2c", "W8"})
    assert block.rung == CredibilityRung.RUNG_4  # gap no longer caps at 2
    assert block.n_claims_audited == block.n_claims_total - n_unaudited
