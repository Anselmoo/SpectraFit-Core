"""SL-11 regression: structure-wire passes must not inflate the rung.

``_compute_rung`` correctly excluded structure (S-prefixed) wire *failures*
from the RUNG_2 fail-floor check, but did not exclude structure-wire *passes*
from `core` (the pass_count source for RUNG_3/RUNG_4) — so a wire set with
few or zero real numerical passes but several passing structure wires could
reach RUNG_4 purely on structural checks, contradicting the function's own
documented intent that structure wires are non-capping ("verify the repo's
self-description, not a run's numbers"). Confirmed by an independent
two-judge panel before this fix landed, including the stronger case: 0 real
numerical passes + 6 structure-wire passes alone reaching RUNG_4.
"""

from __future__ import annotations

from oracles.audit.runner import _compute_rung
from oracles.trust_ledger import CredibilityRung, WireResult, WireStatus


def _w(wire_id: str, status: WireStatus) -> WireResult:
    return WireResult(wire_id=wire_id, name=wire_id, status=status, evidence="stub")


def test_structure_wire_passes_alone_do_not_earn_rung4() -> None:
    """0 real numerical wires + 6 passing structure wires must NOT reach RUNG_4."""
    wires = [_w(f"S{i}", "pass") for i in range(1, 7)]
    assert _compute_rung(wires) != CredibilityRung.RUNG_4
    assert _compute_rung(wires) == CredibilityRung.RUNG_2


def test_few_numerical_passes_plus_structure_passes_does_not_reach_rung4() -> None:
    """2 real numerical passes + 5 structure passes must NOT reach RUNG_4 on the
    strength of the structure wires alone (2 real passes alone stay at RUNG_2)."""
    wires = [_w("W1", "pass"), _w("W2d", "pass")] + [
        _w(f"S{i}", "pass") for i in range(1, 6)
    ]
    assert _compute_rung(wires) == CredibilityRung.RUNG_2


def test_structure_wire_failures_still_do_not_floor_the_rung() -> None:
    """A failing structure wire must still be non-capping — this direction of the
    exclusion (numerical) was already correct before the SL-11 fix and must not
    regress: an otherwise-RUNG_4-earning wire set stays at RUNG_4 with S1='fail'."""
    core_rung4 = [
        _w("W1", "pass"),
        _w("W2a", "pass"),
        _w("W2b", "pass"),
        _w("W2c", "gap"),
        _w("W2d", "pass"),
        _w("W3", "pass"),
        _w("W4", "pass"),
        _w("W5", "skipped"),
        _w("W6", "pass"),
        _w("W7", "pass"),
    ]
    assert _compute_rung(core_rung4) == CredibilityRung.RUNG_4
    assert _compute_rung(core_rung4 + [_w("S1", "fail")]) == CredibilityRung.RUNG_4
