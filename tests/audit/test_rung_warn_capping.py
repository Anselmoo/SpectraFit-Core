"""SL-12 regression: a "warn" on a soft-cap value wire must not be invisible to
the rung ladder.

``_compute_rung`` previously matched only "fail"/"skipped"/"pass"/"gap" — a
soft-cap wire (W2a/W2b/W2c) with status "warn" (a real, disclosed numerical
concern the recompute detected, e.g. W2b's sigma-coverage falling outside its
[0.5, 0.85] target band) contributed to neither pass_count nor unproven_count
and was not caught by the skip-only soft cap either, so a genuinely
miscalibrated run could still reach RUNG_5. Confirmed by an independent
two-judge panel before this fix landed. "warn" must now cap the rung at
RUNG_3, exactly like "skipped" does on the same wires.
"""

from __future__ import annotations

from oracles.audit.runner import _compute_rung
from oracles.trust_ledger import CredibilityRung, WireResult, WireStatus


def _w(wire_id: str, status: WireStatus) -> WireResult:
    return WireResult(wire_id=wire_id, name=wire_id, status=status, evidence="stub")


# Wire set that would otherwise clear the full RUNG_5 ladder (all core pass,
# W8/W10/W11 all pass) — mirrors tests/audit/test_rung_inferential.py's fixture
# shape but with every soft-cap wire at "pass" as the RUNG_5-earning baseline.
def _rung5_baseline(
    *, w2a: WireStatus = "pass", w2b: WireStatus = "pass", w2c: WireStatus = "pass"
) -> list[WireResult]:
    return [
        _w("W1", "pass"),
        _w("W2a", w2a),
        _w("W2b", w2b),
        _w("W2c", w2c),
        _w("W2d", "pass"),
        _w("W3", "pass"),
        _w("W4", "pass"),
        _w("W5", "skipped"),
        _w("W6", "pass"),
        _w("W7", "pass"),
        _w("W8", "pass"),
        _w("W10", "pass"),
        _w("W11", "pass"),
    ]


def test_rung5_baseline_reaches_rung5_when_all_soft_cap_wires_pass() -> None:
    """Sanity check: the fixture itself earns RUNG_5 when nothing is warn/skipped."""
    assert _compute_rung(_rung5_baseline()) == CredibilityRung.RUNG_5


def test_w2b_warn_caps_at_rung3_not_rung5() -> None:
    """A miscalibrated sigma-coverage wire (W2b='warn') must not reach RUNG_5."""
    wires = _rung5_baseline(w2b="warn")
    assert _compute_rung(wires) == CredibilityRung.RUNG_3


def test_w2a_warn_caps_at_rung3() -> None:
    wires = _rung5_baseline(w2a="warn")
    assert _compute_rung(wires) == CredibilityRung.RUNG_3


def test_w2c_warn_caps_at_rung3() -> None:
    wires = _rung5_baseline(w2c="warn")
    assert _compute_rung(wires) == CredibilityRung.RUNG_3


def test_warn_caps_the_same_as_skipped() -> None:
    """'warn' and 'skipped' on the same soft-cap wire must produce the same rung."""
    warn_rung = _compute_rung(_rung5_baseline(w2b="warn"))
    skipped_rung = _compute_rung(_rung5_baseline(w2b="skipped"))
    assert warn_rung == skipped_rung == CredibilityRung.RUNG_3


def test_w2c_gap_is_still_non_capping_unlike_warn() -> None:
    """A disclosed 'gap' (capability absence) must stay exempt — only 'warn'
    (a checked-and-found-a-problem result) triggers the soft cap, not 'gap'."""
    wires = _rung5_baseline(w2c="gap")
    assert _compute_rung(wires) == CredibilityRung.RUNG_5
