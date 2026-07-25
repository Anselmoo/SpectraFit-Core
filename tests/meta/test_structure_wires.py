"""Structure-wire conformance — the repo's self-description must stay true.

The S-wires (:mod:`oracles.audit.structure_wires`) verify that the claims the
tree makes about *itself* have not drifted from the structure: hook
source-of-truth paths exist (S1), INDEX.yaml anchors are triggered or
self-declare MANUAL-ONLY (S2), doc owner-claims resolve to the real definition
(S3), the FFI stub is complete (S4), and the Rust/Python model lists agree (S5).

They are wired into ``run_audit`` (non-capping for now), but a wire that only
runs inside a heavy audit is easy to let rot. This pins them directly: the
moment a hook is re-scoped to a dead path, an anchor is advertised without a
trigger, a doc points at the wrong contract module, the FFI stub drifts, or the
model lists diverge, this test goes red in CI — fast, no benchmark run needed.

    uv run pytest tests/meta/test_structure_wires.py -q
"""

from __future__ import annotations

import pytest

from oracles.audit.structure_wires import S_WIRES, run_structure_wires


def test_all_structure_wires_pass_on_this_repo() -> None:
    """Every S-wire must pass (or skip) — never fail — against the live tree."""
    results = run_structure_wires()
    failures = [
        f"{w.wire_id} {w.name}: {w.evidence}" for w in results if w.status == "fail"
    ]
    assert not failures, "structure self-description has drifted:\n" + "\n".join(
        failures
    )


@pytest.mark.parametrize("wire", S_WIRES, ids=lambda w: w.__name__)
def test_each_structure_wire_is_runnable(wire) -> None:
    """Each wire returns a well-formed WireResult and never raises."""
    result = wire()
    assert result.wire_id.startswith("S")
    assert result.status in {"pass", "fail", "skipped", "gap"}
