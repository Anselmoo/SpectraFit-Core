"""Regression guards for the Plan C2 phase split of ``oracles.synth.build_featured``.

The pre-split function was a single 216-LOC body with CC=44. Plan C2 (refactor
3/4) split it into four phase helpers — truth/grid, per-solver timings,
per-solver profiles, and extras — orchestrated by a thin ``build_featured``.

The refactor is **purely structural**: identical RNG seed → byte-identical
``Featured`` JSON. These tests pin that promise so a later edit that
accidentally re-orders an ``rng.gauss`` call (or adds one) fails loudly here
instead of silently shifting the synthetic fixture every test run.

The fixture itself is consumed by ``tests/integration/benchmark/test_api.py``,
``tests/unit/benchmark/test_contract.py``, and ``tests/unit/benchmark/test_migrate.py``;
those tests already round-trip the report, so a drift in this builder cascades.
"""

from __future__ import annotations

import hashlib
import random

from oracles.bench_contract import Featured, PeakACS
from oracles.synth import (
    _build_featured_extras,
    _build_featured_per_solver_profiles,
    _build_featured_per_solver_timings,
    _build_featured_truth_and_grid,
    build_featured,
)

# Post-call RNG state probes — drawn AFTER `build_featured(rng)` consumes its
# share. If the orchestrator skips a draw or adds one, these shift first.
# Re-pinned for SP-2: `_multidim`/synth's MultiDim is now an N-D fit (no 2-D
# obs/model/resid grids), so build_featured consumes fewer RNG draws.
_EXPECTED_POST_RANDOM = 0.34602308234187307
_EXPECTED_POST_GAUSS = 1.9781145116400793


def test_build_featured_is_deterministic_byte_identical() -> None:
    """Same seed twice → identical JSON (cross-call reproducibility).

    The previous SHA-256 + JSON-length pin (130548 bytes on macOS) was platform
    fragile: CI sees 130540 on Linux because of f64-format drift at the 16th
    decimal in some random draws. The load-bearing invariant is *reproducibility
    at the same seed on the same platform*; the per-platform hash adds no value
    once the C2 refactor has landed (its job was to catch RNG-order changes
    during the split, which the post-call RNG-state probes also catch).
    """
    a = build_featured(random.Random(42)).model_dump_json(by_alias=True)
    b = build_featured(random.Random(42)).model_dump_json(by_alias=True)
    assert a == b, "build_featured drifted between two runs at the same seed"
    # Sanity: the payload is non-trivial. A 1 KB lower bound is safe — a real
    # Featured contains ≥6 backend profiles × ≥4 ndarrays each, so ≥10 KB.
    assert len(a) > 10_000, f"build_featured JSON suspiciously small: {len(a)} bytes"
    # Hash stability is asserted on the same platform: hashing `a` twice in the
    # same process is the only deterministic property of hashlib that does not
    # depend on float formatting.
    assert (
        hashlib.sha256(a.encode()).hexdigest() == hashlib.sha256(b.encode()).hexdigest()
    )


def test_rng_state_after_build_featured_is_pinned() -> None:
    """The exact RNG state after `build_featured` returns is load-bearing.

    Downstream callers (`synth.build_report`) reuse the same `rng` to build the
    suite; if the total number of draws in `build_featured` changes, the suite
    seed shifts and every downstream fixture drifts too.
    """
    rng = random.Random(42)
    _ = build_featured(rng)
    post_random = rng.random()
    post_gauss = rng.gauss(0, 1)
    assert post_random == _EXPECTED_POST_RANDOM, (
        f"rng.random() after build_featured shifted: {post_random!r} != "
        f"{_EXPECTED_POST_RANDOM!r} — a phase added or skipped an RNG draw."
    )
    assert post_gauss == _EXPECTED_POST_GAUSS, (
        f"rng.gauss after build_featured shifted: {post_gauss!r} != "
        f"{_EXPECTED_POST_GAUSS!r} — a phase added or skipped an RNG draw."
    )


def test_phase_truth_and_grid_pins_truth_peaks_and_grid_shape() -> None:
    """Phase 1 is callable in isolation; truth peaks + grid endpoints are pinned."""
    rng = random.Random(42)
    grid = _build_featured_truth_and_grid(rng, n=48)
    assert len(grid.x) == 48
    assert len(grid.ref) == 48
    assert len(grid.guess) == 48
    assert grid.noise == 0.085
    # Truth peaks are constants of the fixture — explicit so a typo here is loud.
    assert grid.truth == [
        PeakACS(a=4.95, c=0.0, s=1.0),
        PeakACS(a=2.30, c=-2.5, s=0.6),
        PeakACS(a=1.65, c=2.4, s=0.8),
    ]
    assert grid.guess_p == [
        PeakACS(a=4.2, c=0.18, s=1.18),
        PeakACS(a=1.9, c=-2.2, s=0.75),
        PeakACS(a=1.3, c=2.7, s=1.0),
    ]
    # Grid endpoints are deterministic functions of n; pin them so an
    # off-by-one in the linspace formula is caught.
    assert grid.x[0] == -5.2
    assert grid.x[-1] == 5.2
    # The first ref point should equal `truth_sum(x[0]) + first_noise`. Verify
    # by re-drawing the first noise sample from a fresh rng and matching.
    rng_probe = random.Random(42)
    first_noise = rng_probe.gauss(0, 0.085)
    noise_free_x0 = grid.ref[0] - first_noise
    # Compare against the closed-form noise-free reference (truth evaluated at
    # x[0]); allows a tiny float-arithmetic tolerance.
    from oracles.synth import _g

    expected_noise_free_x0 = sum(_g(grid.x[0], p.a, p.c, p.s) for p in grid.truth)
    assert abs(noise_free_x0 - expected_noise_free_x0) < 1e-12


def test_phase_per_solver_timings_is_pure() -> None:
    """Phase 2 has no RNG dependency; constants are pinned."""
    timings = _build_featured_per_solver_timings()
    # Solver roster ordering matches `_SOLVER_IDS` (oracles.cases.SOLVER_META).
    assert set(timings.perturb.keys()) == set(timings.base_ms.keys())
    assert "spectrafit" in timings.base_ms
    assert "lmfit" in timings.base_ms
    assert timings.base_ms["lmfit"] == 4.9  # the speedup baseline anchor
    assert timings.n_grid == [128, 256, 512, 1024, 2048, 4096]
    assert timings.schedule == [1, 5, 10, 25, 50, 100]
    assert timings.runs_sched == [1, 2, 5, 10, 25, 50]
    assert timings.n_params == 9
    assert timings.param_names[0] == "g1.amplitude"
    assert timings.param_names[-1] == "g3.sigma"


def test_phase_composition_matches_orchestrator() -> None:
    """Calling phases in sequence yields the same JSON as `build_featured`.

    This is the structural regression guard: if a phase helper is rewritten to
    skip / add an RNG draw, the manually-composed `Featured` here diverges
    from the orchestrator's, even though the byte-identical hash test may still
    pass on the orchestrator alone.
    """
    # Reference: orchestrator output.
    ref = build_featured(random.Random(42)).model_dump_json(by_alias=True)

    # Manually compose: must follow the orchestrator's exact phase order.
    rng = random.Random(42)
    n = 48
    grid = _build_featured_truth_and_grid(rng, n)
    timings = _build_featured_per_solver_timings()
    bundle = _build_featured_per_solver_profiles(rng, grid=grid, timings=timings, n=n)
    extras = _build_featured_extras(
        rng, grid=grid, timings=timings, fit_params=bundle.fit_params
    )
    composed = Featured(
        id="RL-031",
        name="tri-gaussian · reality-like + 8.5% noise",
        category="reality",
        x=grid.x,
        ref=grid.ref,
        guess=grid.guess,
        truth=grid.truth,
        noise=grid.noise,
        baseline=timings.base_ms["lmfit"],
        profiles=bundle.profiles,
        peaks=extras.peaks,
        param_names=timings.param_names,
        corr=extras.corr,
        n_grid=timings.n_grid,
        schedule=timings.schedule,
        runs_sched=timings.runs_sched,
        cross_n=3100.0,
        multidim=extras.multidim,
    )
    assert composed.model_dump_json(by_alias=True) == ref


def test_phase_per_solver_profiles_covers_full_solver_roster() -> None:
    """Phase 3 produces one profile per solver and the matching fit_params dict."""
    rng = random.Random(42)
    grid = _build_featured_truth_and_grid(rng, n=48)
    timings = _build_featured_per_solver_timings()
    bundle = _build_featured_per_solver_profiles(rng, grid=grid, timings=timings, n=48)
    # Same key set on both dicts — they're built in lockstep.
    assert set(bundle.profiles.keys()) == set(bundle.fit_params.keys())
    # Every solver in the canonical roster is present.
    assert "spectrafit" in bundle.profiles
    assert "lmfit" in bundle.profiles
    # Each fit_params entry has exactly 3 peaks (tri-gaussian fixture).
    for sid, pf in bundle.fit_params.items():
        assert len(pf) == 3, f"{sid} fit_params lost a peak: {len(pf)}"
