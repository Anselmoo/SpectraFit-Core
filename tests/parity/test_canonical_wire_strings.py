"""Canonical wire-format strings — gate states + backend ids (Top-10 #7).

Mirrors the Rust-side `model_type_as_str_matches_serde_wire_for_every_variant`
parity test in spectrafit-types, applied to the two remaining cross-cutting
string-typed wire fields in the BenchReport contract:

* ``GateState`` — the 3-axis pass/warn/fail level the `spc-bench gate --json`
  output carries; the web `GateBadge.tsx` was missing the `"warn"` state until
  this cycle, exemplifying the wire-drift bug class.
* Backend solver ids — `SolverId` is `str` for forward-compat, but the
  *currently known* roster is pinned so a typo (`"lmift"` for `"lmfit"`) is
  surfaced at test time, not at benchmark time.

Both surfaces stay `str` on the wire so the contract is open for extension;
this test catches drift between the producer (Python contract.py + cli.py)
and the consumer (web TS, future Rust calls).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import get_args

from oracles.bench_contract import (
    GATE_RANK,
    GATE_STATES,
    KNOWN_SOLVER_IDS,
    GateState,
)


# ---------------------------------------------------------------------------
# GateState — exhaustive roster + rank consistency
# ---------------------------------------------------------------------------


def test_gate_states_exhaustively_match_literal() -> None:
    """`GATE_STATES` lists every variant of the `GateState` Literal."""
    literal_values = set(get_args(GateState))
    roster_values = set(GATE_STATES)
    assert literal_values == roster_values, (
        f"GateState Literal {literal_values} disagrees with GATE_STATES roster {roster_values}"
    )


def test_gate_rank_covers_every_state_uniquely() -> None:
    """`GATE_RANK` has one entry per gate state and ranks them ``pass < warn < fail``."""
    assert set(GATE_RANK.keys()) == set(GATE_STATES)
    ranks = [GATE_RANK[s] for s in GATE_STATES]
    assert ranks == sorted(ranks), "GATE_STATES order does not match GATE_RANK order"
    # Specifically: pass=0, warn=1, fail=2 (worst wins).
    assert GATE_RANK["pass"] < GATE_RANK["warn"] < GATE_RANK["fail"]


def test_gate_state_wire_format_is_lowercase() -> None:
    """Wire format is lowercase. CLI emits `"pass"/"warn"/"fail"` in
    `spc-bench gate --json`; the web is free to uppercase on render but must
    never RE-EMIT uppercase on the wire."""
    for state in GATE_STATES:
        assert state == state.lower(), f"GateState {state!r} is not lowercase"


# ---------------------------------------------------------------------------
# Backend ids — currently-known roster pinned, drift surfaced as test failure
# ---------------------------------------------------------------------------


def test_known_solver_ids_is_a_frozenset_of_strings() -> None:
    """The roster is immutable + str-typed so a downstream consumer cannot
    mutate it at runtime."""
    assert isinstance(KNOWN_SOLVER_IDS, frozenset)
    assert all(isinstance(s, str) for s in KNOWN_SOLVER_IDS)


def test_known_solver_ids_is_lowercase_with_dashes() -> None:
    """All ids match ``[a-z][a-z0-9-]*`` — lowercase, no underscores or dots."""
    pattern = re.compile(r"^[a-z][a-z0-9-]*$")
    for sid in KNOWN_SOLVER_IDS:
        assert pattern.match(sid) is not None, (
            f"Solver id {sid!r} violates the lowercase-dash convention"
        )


def test_known_solver_ids_includes_baseline_default() -> None:
    """The baseline_solver_id default (``"lmfit"``) must be in the roster.

    Catches the regression: someone removes `lmfit` from the roster while
    leaving `BenchReport.baseline_solver_id: str = "lmfit"` (the default),
    producing a contract whose default is not a recognised id.
    """
    from oracles.bench_contract import BenchReport

    field = BenchReport.model_fields["baseline_solver_id"]
    default = field.default
    assert default in KNOWN_SOLVER_IDS, (
        f"baseline_solver_id default {default!r} not in KNOWN_SOLVER_IDS"
    )


# ---------------------------------------------------------------------------
# Source-drift surface scan: catch new gate-state strings introduced inline.
#
# Heuristic: any *.py file under python/extras/bench/ that contains the
# strings "fail"/"warn"/"pass" in a *gate* context but does not import GATE_STATES
# is a candidate for refactoring. This is a SOFT signal — the test does not
# fail on drift, it asserts that the canonical declarations live in contract.py
# and are importable.
# ---------------------------------------------------------------------------


def test_canonical_declarations_are_importable_from_contract() -> None:
    """All wire-string canonicals are accessible via `from oracles.bench_contract import ...`."""
    from oracles import bench_contract as contract

    assert hasattr(contract, "GateState")
    assert hasattr(contract, "GATE_STATES")
    assert hasattr(contract, "GATE_RANK")
    assert hasattr(contract, "KNOWN_SOLVER_IDS")


def test_contract_module_is_the_single_source_of_truth() -> None:
    """No other module under python/extras/bench/ should re-declare a frozenset
    of solver ids or a tuple of gate-state literals — that would be the start
    of the drift bug Top-10 #7 was raised to prevent.

    Heuristic match: an inline `frozenset({"spectrafit", "lmfit", ...})` literal,
    or `("pass", "warn", "fail")` literal, outside contract.py is flagged.
    """
    bench_root = (
        Path(__file__).resolve().parent.parent.parent / "python" / "extras" / "bench"
    )
    forbidden_patterns = [
        re.compile(r'frozenset\(\{[^}]*"spectrafit"'),
        re.compile(r'\("pass",\s*"warn",\s*"fail"\)'),
    ]
    offenders: list[str] = []
    for py in bench_root.rglob("*.py"):
        if py.name == "contract.py":
            continue
        if "__pycache__" in py.parts:
            continue
        text = py.read_text(encoding="utf-8")
        for pat in forbidden_patterns:
            if pat.search(text):
                offenders.append(f"{py.relative_to(bench_root)} matches {pat.pattern}")
    assert not offenders, (
        "Inline wire-string declarations found outside contract.py — "
        "import from `oracles.bench_contract` instead:\n  " + "\n  ".join(offenders)
    )
