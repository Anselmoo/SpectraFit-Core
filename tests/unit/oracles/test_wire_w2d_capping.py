"""EF-PY-13: W2d in UNKNOWN/no-cache state must CAP the rung.

The solver-output oracle (W2d) verifies that spectrafit's fitted params + σ
match scipy.optimize.least_squares — a value-oracle wire. On a fresh checkout
with no .pytest_cache, the lastfailed cache is absent, so _test_state returns
UNKNOWN and _status_for maps that to "skipped".

Prior to the fix, "skipped" on W2d was soft-capping (prevented RUNG_4/5 but
allowed RUNG_3). The fix promotes W2d UNKNOWN to CAPPING — treated the same
as a "fail" for rung purposes — so an unverified value oracle does NOT allow
the dashboard to silently claim a RUNG_3 or higher credibility rung.

This mirrors the runner.py:50-53 pattern for W2a/W2b/W2c, but goes further:
UNKNOWN on W2d is treated as a hard cap (like "fail"), not just the soft cap
at RUNG_3 that "skipped" provides via the value_wire_skipped guard.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from oracles.audit.runner import _compute_rung
from oracles.audit.wires import wire_w2d_solver_output_oracle
from oracles.trust_ledger import CredibilityRung, WireResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _wires(statuses: dict[str, str]) -> list[WireResult]:
    """Build a minimal wire list from a status dict."""
    return [
        WireResult(wire_id=k, name=k, status=v, evidence="stub")
        for k, v in statuses.items()
    ]


# A configuration that earns RUNG_4 when all core value wires are verified.
# W2c is "gap" (capability gap — non-capping by design), W5 "skipped" (CI-only).
_RUNG4_BASE = {
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


# ---------------------------------------------------------------------------
# wire_w2d_solver_output_oracle() on a fresh checkout (no cache)
# ---------------------------------------------------------------------------

def test_w2d_no_cache_returns_skipped_status(tmp_path: Path) -> None:
    """Without a lastfailed cache, wire_w2d returns 'skipped' (no pass-by-absence)."""
    absent = tmp_path / "nonexistent_cache"
    with patch("oracles.audit.wires._LASTFAILED_CACHE", absent):
        results = wire_w2d_solver_output_oracle()
    assert len(results) == 1
    assert results[0].wire_id == "W2d"
    assert results[0].status == "skipped"


# ---------------------------------------------------------------------------
# EF-PY-13: W2d "skipped" (UNKNOWN cache) must cap the rung
# ---------------------------------------------------------------------------

def test_w2d_skipped_caps_rung_below_rung3(tmp_path: Path) -> None:
    """W2d UNKNOWN/skipped must prevent the rung from reaching RUNG_3 or higher.

    A rung-4-worthy configuration with W2d skipped (no cache) must produce
    a rung strictly below RUNG_3 — the value oracle is unverified and the
    credibility claim must not be silently inflated.
    """
    statuses = {**_RUNG4_BASE, "W2d": "skipped"}
    rung = _compute_rung(_wires(statuses))
    assert rung < CredibilityRung.RUNG_3, (
        f"W2d skipped (UNKNOWN cache) should cap rung below RUNG_3, got {rung}"
    )


def test_w2d_skipped_caps_rung_at_rung2(tmp_path: Path) -> None:
    """W2d UNKNOWN caps the rung at RUNG_2 — same behaviour as a 'fail'."""
    statuses = {**_RUNG4_BASE, "W2d": "skipped"}
    rung = _compute_rung(_wires(statuses))
    assert rung == CredibilityRung.RUNG_2, (
        f"W2d skipped should produce RUNG_2 (value oracle unverified), got {rung}"
    )


def test_w2d_pass_does_not_cap_rung() -> None:
    """When W2d passes, the rung should be able to reach RUNG_4 (baseline holds)."""
    statuses = {**_RUNG4_BASE, "W2d": "pass"}
    rung = _compute_rung(_wires(statuses))
    assert rung >= CredibilityRung.RUNG_4, (
        f"W2d pass should not cap the rung; expected >= RUNG_4, got {rung}"
    )


def test_w2d_fail_caps_rung_at_rung2() -> None:
    """W2d fail caps at RUNG_2 (genuine failure — existing behaviour, must hold)."""
    statuses = {**_RUNG4_BASE, "W2d": "fail"}
    rung = _compute_rung(_wires(statuses))
    assert rung == CredibilityRung.RUNG_2


def test_w2d_unknown_via_absent_cache_caps_rung(tmp_path: Path) -> None:
    """Full integration: absent cache file → W2d UNKNOWN → rung caps at RUNG_2.

    Exercises the full wire → _compute_rung pipeline so the fix is tested
    end-to-end, not just at the _compute_rung level.
    """
    absent = tmp_path / "nonexistent_cache"
    with patch("oracles.audit.wires._LASTFAILED_CACHE", absent):
        w2d_wires = wire_w2d_solver_output_oracle()

    # Build a full rung-4-worthy wire list with the fresh-checkout W2d.
    full_wires = _wires(_RUNG4_BASE) + w2d_wires
    rung = _compute_rung(full_wires)
    assert rung == CredibilityRung.RUNG_2, (
        f"Fresh checkout (no cache) → W2d UNKNOWN → expected RUNG_2, got {rung}"
    )
