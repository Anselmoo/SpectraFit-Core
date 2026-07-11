"""V4 — no silent skip: a skipped *audited value wire* caps the credibility rung.

A "skipped" status on a wire that verifies a numerical value/claim (W2a metric
identity, W2b coverage, W2c κ(J), W2d solver-output oracle, W8 NIST) means that
value was never verified — it must NOT silently pass through to the top rung.
A disclosed "gap" (e.g. W2c κ(J) capability absence) is honest and non-capping;
a "skipped" on the visible/render lane (W5) is by-design conservative, not a
value hole.
"""

from __future__ import annotations

from oracles.audit.runner import _compute_rung
from oracles.trust_ledger import CredibilityRung, WireResult


def _wires(**overrides: str) -> list[WireResult]:
    """Production-like wire set (matches run_026): every value wire passes,
    W2c is a disclosed gap, W5 (render) is skipped → earns RUNG_5.

    Updated for cycle-5: W10 (σ-calibration) and W11 (speed inference) are
    now required for RUNG_5 and included as "pass" in the base fixture.
    """
    base = {
        "W1": "pass", "W2a": "pass", "W2b": "pass", "W2c": "gap", "W2d": "pass",
        "W3": "pass", "W4": "pass", "W5": "skipped", "W6": "pass", "W7": "pass",
        "W8": "pass", "W10": "pass", "W11": "pass",
    }
    base.update(overrides)
    return [WireResult(wire_id=k, name=k, status=v, evidence="t") for k, v in base.items()]


def test_production_like_earns_rung5() -> None:
    assert _compute_rung(_wires()) == CredibilityRung.RUNG_5


def test_skipped_value_wire_caps_below_rung5() -> None:
    # W2a (metric identity) never ran → its claim is unverified → cannot reach the
    # top rung, even though 7 other core wires still pass (the old silent-pass bug).
    capped = _compute_rung(_wires(W2a="skipped"))
    assert capped < CredibilityRung.RUNG_5
    assert capped <= CredibilityRung.RUNG_3


def test_skipped_solver_oracle_caps() -> None:
    assert _compute_rung(_wires(W2d="skipped")) < CredibilityRung.RUNG_5


def test_disclosed_gap_does_not_cap() -> None:
    # W2c as a disclosed κ(J) gap is honest, non-capping — RUNG_5 still reachable.
    assert _compute_rung(_wires(W2c="gap")) == CredibilityRung.RUNG_5


def test_render_lane_skip_does_not_cap() -> None:
    # W5 (visible/render lane) is conservatively skipped by design, not a value
    # coverage hole — it must not cap the value-credibility rung.
    assert _compute_rung(_wires(W5="skipped")) == CredibilityRung.RUNG_5


def test_failed_wire_still_caps_at_rung2() -> None:
    assert _compute_rung(_wires(W2a="fail")) == CredibilityRung.RUNG_2
