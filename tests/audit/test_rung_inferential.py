"""Task 5.6 — RUNG_5 now requires the inferential wires W10 ∧ W11.

RUNG_5 was previously gated on W8 (NIST StRD) alone.  After this cycle it
additionally requires W10 (σ-calibration) and W11 (speed inference) to pass.
NIST-only (W8 pass, W10/W11 absent or skipped) honestly caps at RUNG_4.
"""

from __future__ import annotations

import pytest

from oracles.audit.runner import _compute_rung
from oracles.trust_ledger import (
    CredibilityRung,
    NistDataset,
    NistParam,
    NistValidation,
    TrustBlock,
    WireResult,
    WireStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _w(wire_id: str, status: WireStatus) -> WireResult:
    return WireResult(wire_id=wire_id, name=wire_id, status=status, evidence="stub")


# Core wire set that clears the RUNG_4 ladder + W8 pass.
# W2c is a disclosed gap (non-capping); W5 skipped (render-only, non-capping).
# W2d must be "pass" (hard-cap: skipped caps at RUNG_2).
_CORE_RUNG4_WITH_W8: list[WireResult] = [
    _w("W1",  "pass"),
    _w("W2a", "pass"),
    _w("W2b", "pass"),
    _w("W2c", "gap"),
    _w("W2d", "pass"),
    _w("W3",  "pass"),
    _w("W4",  "pass"),
    _w("W5",  "skipped"),
    _w("W6",  "pass"),
    _w("W7",  "pass"),
    _w("W8",  "pass"),
]


# ---------------------------------------------------------------------------
# Fixture helper for building a minimal passing NistValidation for TrustBlock
# ---------------------------------------------------------------------------

def _passing_nist() -> NistValidation:
    param = NistParam(name="b1", certified=1.0, fitted=1.0, sig_figs_agreed=15.0)
    ds = NistDataset(
        name="Gauss1", model="three-term Gaussian", n_params=1,
        params=[param], min_sig_figs=15.0, passed=True,
    )
    return NistValidation(
        threshold_sig_figs=4.0, datasets=[ds], min_sig_figs=15.0, passed=True
    )


# ---------------------------------------------------------------------------
# _compute_rung: RUNG_5 gate tests (TDD red → green)
# ---------------------------------------------------------------------------

def test_rung5_requires_w10_w11_pass() -> None:
    """W8 + W10 pass + W11 pass → RUNG_5."""
    wires = _CORE_RUNG4_WITH_W8 + [_w("W10", "pass"), _w("W11", "pass")]
    assert _compute_rung(wires) == CredibilityRung.RUNG_5


def test_nist_only_caps_at_rung4_without_inference() -> None:
    """W8 pass + W10 skipped + W11 skipped → RUNG_4 (no pass-by-absence at ceiling)."""
    wires = _CORE_RUNG4_WITH_W8 + [_w("W10", "skipped"), _w("W11", "skipped")]
    assert _compute_rung(wires) == CredibilityRung.RUNG_4


def test_nist_only_no_w10_w11_caps_at_rung4() -> None:
    """W8 pass but W10/W11 entirely absent → RUNG_4 (pre-cycle-5 payload)."""
    assert _compute_rung(_CORE_RUNG4_WITH_W8) == CredibilityRung.RUNG_4


def test_failing_w10_caps_below_rung5() -> None:
    """W10 fail + W11 pass → ≤ RUNG_4."""
    wires = _CORE_RUNG4_WITH_W8 + [_w("W10", "fail"), _w("W11", "pass")]
    assert _compute_rung(wires) <= CredibilityRung.RUNG_4


def test_failing_w11_caps_below_rung5() -> None:
    """W10 pass + W11 fail → ≤ RUNG_4 (W11 fail counts as genuine failure → RUNG_2)."""
    wires = _CORE_RUNG4_WITH_W8 + [_w("W10", "pass"), _w("W11", "fail")]
    assert _compute_rung(wires) <= CredibilityRung.RUNG_4


def test_w10_skipped_w11_pass_caps_at_rung4() -> None:
    """W10 skipped (inference absent) + W11 pass → still RUNG_4 (both required)."""
    wires = _CORE_RUNG4_WITH_W8 + [_w("W10", "skipped"), _w("W11", "pass")]
    assert _compute_rung(wires) == CredibilityRung.RUNG_4


def test_w10_pass_w11_skipped_caps_at_rung4() -> None:
    """W10 pass + W11 skipped (inference absent) → still RUNG_4 (both required)."""
    wires = _CORE_RUNG4_WITH_W8 + [_w("W10", "pass"), _w("W11", "skipped")]
    assert _compute_rung(wires) == CredibilityRung.RUNG_4


def test_lower_rung_fail_still_caps_at_rung2_even_with_w10_w11() -> None:
    """A genuine lower-rung failure caps at RUNG_2 even when W10/W11 pass."""
    wires = [
        _w("W1",  "fail"),   # genuine failure → hard cap
        _w("W2a", "pass"),
        _w("W2b", "pass"),
        _w("W2c", "gap"),
        _w("W2d", "pass"),
        _w("W3",  "pass"),
        _w("W4",  "pass"),
        _w("W5",  "skipped"),
        _w("W6",  "pass"),
        _w("W7",  "pass"),
        _w("W8",  "pass"),
        _w("W10", "pass"),
        _w("W11", "pass"),
    ]
    assert _compute_rung(wires) == CredibilityRung.RUNG_2


# ---------------------------------------------------------------------------
# TrustBlock validator: claim↔evidence integrity for RUNG_5
# ---------------------------------------------------------------------------

def _rung5_wires_passing() -> list[WireResult]:
    """Wire list that satisfies the new RUNG_5 claim↔evidence requirements."""
    return _CORE_RUNG4_WITH_W8 + [_w("W10", "pass"), _w("W11", "pass")]


def test_trustblock_rung5_with_passing_wires_and_nist_constructs() -> None:
    """TrustBlock(rung=RUNG_5, ...) succeeds when W10 + W11 pass + nist passed."""
    block = TrustBlock(
        rung=CredibilityRung.RUNG_5,
        wires=_rung5_wires_passing(),
        n_claims_audited=10,
        n_claims_total=10,
        nist_validation=_passing_nist(),
    )
    assert block.rung == CredibilityRung.RUNG_5


def test_trustblock_rung5_without_w10_raises() -> None:
    """TrustBlock(rung=RUNG_5) without a passing W10 wire raises ValueError."""
    wires = _CORE_RUNG4_WITH_W8 + [_w("W10", "skipped"), _w("W11", "pass")]
    with pytest.raises(ValueError, match="W10"):
        TrustBlock(
            rung=CredibilityRung.RUNG_5,
            wires=wires,
            n_claims_audited=10,
            n_claims_total=10,
            nist_validation=_passing_nist(),
        )


def test_trustblock_rung5_without_w11_raises() -> None:
    """TrustBlock(rung=RUNG_5) without a passing W11 wire raises ValueError."""
    wires = _CORE_RUNG4_WITH_W8 + [_w("W10", "pass"), _w("W11", "skipped")]
    with pytest.raises(ValueError, match="W11"):
        TrustBlock(
            rung=CredibilityRung.RUNG_5,
            wires=wires,
            n_claims_audited=10,
            n_claims_total=10,
            nist_validation=_passing_nist(),
        )


def test_trustblock_rung5_without_nist_raises() -> None:
    """TrustBlock(rung=RUNG_5) still requires nist_validation (existing behaviour)."""
    wires = _rung5_wires_passing()
    with pytest.raises(ValueError, match="nist_validation"):
        TrustBlock(
            rung=CredibilityRung.RUNG_5,
            wires=wires,
            n_claims_audited=10,
            n_claims_total=10,
            nist_validation=None,
        )


def test_trustblock_rung5_with_w10_w11_absent_from_wires_raises() -> None:
    """TrustBlock(rung=RUNG_5) with no W10/W11 in wires at all raises ValueError."""
    with pytest.raises(ValueError, match="W10"):
        TrustBlock(
            rung=CredibilityRung.RUNG_5,
            wires=_CORE_RUNG4_WITH_W8,  # no W10 or W11
            n_claims_audited=10,
            n_claims_total=10,
            nist_validation=_passing_nist(),
        )
