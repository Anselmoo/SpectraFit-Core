"""Wire W6 — gate state is wire-format-typed and emitted into the manifest.

Today: cli.py computes "pass"|"warn"|"fail"; GateBadge.tsx recomputes UPPERCASE
independently from regression flags. This test pins the Python side; a vitest
sibling pins the TS side. After this task there is ONE source of truth.
"""

from __future__ import annotations

import json

import pytest

from oracles.bench_contract import GateState
from oracles.reports import REPORTS_ROOT


def test_gate_state_is_a_literal_type():
    """The contract must declare gate_state as a closed Literal, not str."""
    import typing

    args = typing.get_args(GateState)
    assert set(args) == {"pass", "warn", "fail"}, (
        f"GateState changed: {args} — TS side (web/src/views/GateBadge.tsx) must be updated too"
    )


def test_manifest_carries_gate_state():
    runs = sorted(REPORTS_ROOT.glob("benchmark/*/manifest.json"), reverse=True)
    if not runs:
        pytest.skip("no run on disk")
    manifest = json.loads(runs[0].read_text())
    assert "gate_state" in manifest or "gateState" in manifest, (
        "manifest must carry gate_state so the web UI does not have to recompute it"
    )
