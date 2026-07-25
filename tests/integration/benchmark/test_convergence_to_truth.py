"""V&V — the REAL convergence-to-truth metric (Invariant V, Phase 4).

The benchmark engine now computes, for spectrafit on a synthetic case, the
scale-normalized per-iteration distance of the parameter vector to the known
truth, dₖ = ‖(θₖ − θ_true)/s‖₂ (`BackendProfile.theta_distance`) — the REAL
metric that replaces the χ²-floor proxy. This pins the Stage-1 acceptance
criterion (DECISIONS.md 2026-06-13): the distance decreases and ends at ≤ the
recovery tolerance.

Cost note (pipeline 807266, test:python 60-min llvm-cov timeout): under
coverage instrumentation a real fit is dramatically slower, so this V&V runs
``build_report`` exactly ONCE (a single module fixture, reused by every test)
on the cheapest catalog that still proves the metric — one featured case, a
single grid point (``ngrid=[128]``), and the minimum backend pair that lets
the assertions discriminate: spectrafit (the subject, which records a real θ
trajectory) plus one oracle (lmfit, which must carry ``None``). This keeps the
convergence-to-truth assertions fully meaningful while cutting the fit work by
~45× vs the full 6-backend / 2-grid build that previously ran twice.
"""

from __future__ import annotations

import pytest

from oracles.engine import build_report
from oracles.backends import get_backends
from oracles.cases import build_specs, materialize


@pytest.fixture(scope="module")
def featured_block():
    """Build the featured V&V report ONCE and share it across every test.

    Restricted to spectrafit + lmfit so the run carries (a) a real θ trajectory
    on the subject and (b) at least one oracle that must expose ``None`` — the
    minimum needed for all three assertions below. Building once (instead of the
    prior two builds) and on this lean backend pair is what keeps the
    instrumented ``test:python`` job inside its wall-clock budget.
    """
    specs = build_specs()
    featured = next(s for s in specs if s.featured)
    oracle_backends = ("spectrafit", "lmfit")
    backends = [b for b in get_backends() if b.name in oracle_backends]
    report = build_report(
        n_reps=1,
        n_mc=2,
        catalog=[materialize(featured)],
        ngrid=[128],
        backends=backends,
    )
    return report.analyzed[0]


@pytest.fixture(scope="module")
def featured_profile(featured_block):
    return featured_block.profiles["spectrafit"]


def test_theta_distance_is_real_not_a_proxy(featured_profile) -> None:
    td = featured_profile.theta_distance
    assert td is not None, (
        "spectrafit must expose a REAL θ-distance series on a synthetic case "
        "(per-iteration θ now crosses the PyO3 boundary)"
    )
    # Lock-step with the χ² descent series (recorded at the same accepted points).
    assert len(td) == len(featured_profile.conv)
    assert len(td) >= 2


def test_theta_distance_converges_to_truth(featured_profile) -> None:
    """Stage-1 V&V: dₖ decreases from the initial guess to ≤ recovery tolerance."""
    td = featured_profile.theta_distance
    assert td is not None
    assert td[-1] < td[0], f"θ did not approach truth: {td[0]:.4g} -> {td[-1]:.4g}"
    assert td[-1] < 0.1, f"final θ-distance to truth too large: {td[-1]:.4g}"


def test_oracle_backends_have_no_theta_distance(featured_block) -> None:
    """Only spectrafit records a θ trajectory; oracle backends carry None
    (honest — they expose no per-iteration parameters)."""
    profiles = featured_block.profiles
    # The lean backend pair still includes at least one oracle to discriminate.
    assert any(sid != "spectrafit" for sid in profiles), (
        "fixture must include an oracle backend so the None assertion has teeth"
    )
    for solver_id, prof in profiles.items():
        if solver_id != "spectrafit":
            assert prof.theta_distance is None, (
                f"{solver_id} should not fabricate a θ-distance series"
            )
