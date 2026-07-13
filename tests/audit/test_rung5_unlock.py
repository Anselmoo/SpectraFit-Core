"""A7 — honest RUNG_5 unlock via W8 (NIST StRD external validation).

RUNG_5 is reserved for "independent differential validation + UQ (external
replication)". W8 (NIST certified-value validation) is exactly that evidence.
When W8 passes AND the lower rungs hold (the prior RUNG_4 condition), the earned
rung reaches 5. When W8 is absent / skipped, the rung caps at the prior 4.
"""
from __future__ import annotations

from oracles.audit.runner import _compute_rung
from oracles.trust_ledger import CredibilityRung, WireResult, WireStatus


def _wires(statuses: dict[str, WireStatus]) -> list[WireResult]:
    return [
        WireResult(wire_id=k, name=k, status=v, evidence="stub")
        for k, v in statuses.items()
    ]


_RUNG4_BASE: dict[str, WireStatus] = {
    "W1": "pass", "W2a": "pass", "W2b": "pass", "W2c": "gap",
    "W3": "pass", "W4": "pass", "W5": "skipped", "W6": "pass", "W7": "pass",
}


def test_w8_pass_reaches_rung_5() -> None:
    # Cycle-5: RUNG_5 now requires W8 ∧ W10 ∧ W11 all pass.
    statuses: dict[str, WireStatus] = {**_RUNG4_BASE, "W8": "pass", "W10": "pass", "W11": "pass"}
    assert _compute_rung(_wires(statuses)) == CredibilityRung.RUNG_5


def test_w8_skipped_caps_at_rung_4() -> None:
    statuses: dict[str, WireStatus] = {**_RUNG4_BASE, "W8": "skipped"}
    assert _compute_rung(_wires(statuses)) == CredibilityRung.RUNG_4


def test_w8_absent_caps_at_rung_4() -> None:
    # No W8 entry at all (a payload that predates A7).
    assert _compute_rung(_wires(_RUNG4_BASE)) == CredibilityRung.RUNG_4


def test_w8_pass_but_lower_rung_fails_does_not_force_5() -> None:
    # A genuine lower-rung failure caps at RUNG_2 even with W8 passing.
    statuses: dict[str, WireStatus] = {**_RUNG4_BASE, "W2a": "fail", "W8": "pass"}
    assert _compute_rung(_wires(statuses)) == CredibilityRung.RUNG_2


def test_w8_pass_but_rung_4_floor_not_met_does_not_reach_5() -> None:
    # If too few core wires pass to clear RUNG_4, W8 alone cannot vault to 5.
    statuses: dict[str, WireStatus] = {
        "W1": "pass", "W2a": "skipped", "W2b": "skipped", "W2c": "gap",
        "W3": "skipped", "W4": "skipped", "W5": "skipped", "W6": "pass",
        "W7": "pass", "W8": "pass",
    }
    assert _compute_rung(_wires(statuses)) < CredibilityRung.RUNG_5
