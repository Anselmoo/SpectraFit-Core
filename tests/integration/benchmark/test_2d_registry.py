"""Scaffold + xfail contract pin for 2-D CaseSpec registry promotion (Cycle 13).

Pins the desired API state: a ``CaseSpec`` with ``dimensions=2`` and model
``gaussian2d`` can be materialized via the registry and produce the same shape
``MultiDim``-bearing ``Featured`` payload that ``engine._multidim()`` currently
produces inline.

The field ``dimensions: Literal[1, 2]`` does not yet exist on ``CaseSpec``
(Cycle 13 is design + scaffold only); this test is therefore marked
``xfail`` so it:

- Passes the suite today (xfailed, not errored).
- Becomes xpassed — and thus fails the suite — the moment the
  implementation lands, reminding the implementer to flip the marker.

See the ADR in ``DECISIONS.md`` titled
``[2026-06-09] Andon-loop Cycle 13: scaffold for 2-D promotion into CaseSpec registry``.
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Guard: the test must import cleanly even without the `dimensions` field.
# We probe for the field before attempting construction.
# ---------------------------------------------------------------------------
from oracles.cases import CaseSpec, GaussianSpec, materialize
from oracles.bench_contract import MultiDim


def _has_dimensions_field() -> bool:
    """Return True once CaseSpec carries a `dimensions` discriminant field."""
    return "dimensions" in CaseSpec.model_fields


# ---------------------------------------------------------------------------
# The xfail contract-pin test
# ---------------------------------------------------------------------------
@pytest.mark.xfail(
    reason=(
        "Cycle 13 design landed; implementation pending (Cycle 17 candidate). "
        "CaseSpec does not yet carry `dimensions: Literal[1, 2]`; "
        "flip to xpass once the 2-D registry path is wired."
    ),
    strict=True,
)
def test_casespec_dimensions_2_materializes_via_registry() -> None:
    """A CaseSpec(dimensions=2, gaussian2d) materializes and produces a MultiDim payload.

    Desired final state (Cycle 17):
    1. CaseSpec accepts ``dimensions: Literal[1, 2] = 1``.
    2. ``materialize(spec)`` dispatches to ``_materialize_2d()`` when
       ``spec.dimensions == 2``, lifting the body of ``engine._multidim()``.
    3. The returned ``BenchCase`` (or a new ``BenchCase2D``) can be passed to
       ``run_featured`` and produces a ``Featured`` with a non-None ``multidim``.

    The test is intentionally implementation-agnostic on BenchCase shape; the
    key assertion is that ``dimensions=2`` is *accepted* and that the materialized
    result carries the ``MultiDim``-shaped payload.
    """
    # Step 1: CaseSpec must accept dimensions=2 without ValidationError.
    # Currently raises pydantic.ValidationError (extra field forbidden) or
    # TypeError, which is the xfail trigger.
    assert _has_dimensions_field(), (
        "CaseSpec has no `dimensions` field — implementation not yet landed"
    )

    spec = CaseSpec(
        id="TST-2D-001",
        name="2-D gaussian scaffold (Cycle 13 contract pin)",
        category="easy",
        difficulty=0.2,
        components=[GaussianSpec(amplitude=4.0, center=0.0, sigma=1.0)],
        x_min=-5.0,
        x_max=5.0,
        n_points=64,
        noise=0.02,
        dimensions=2,  # type: ignore[call-arg]  # field absent until Cycle 17
    )
    assert spec.dimensions == 2  # type: ignore[attr-defined]

    # Step 2: materialize must not raise and must return an object carrying the
    # 2-D payload (exact type TBD in the implementation cycle).
    result = materialize(spec)

    # Step 3: result must carry a MultiDim-shaped payload accessible via the
    # same contract path the engine already populates.
    multidim = getattr(result, "multidim", None)
    assert multidim is not None, "materialized 2-D case carries no multidim payload"
    assert isinstance(multidim, MultiDim), (
        f"multidim payload is {type(multidim)!r}, expected MultiDim"
    )
    assert multidim.nx > 0 and multidim.ny > 0
