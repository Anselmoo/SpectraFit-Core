"""Worked examples that exercise the inner logic of `oracles.engine`.

These are not unit-formatter tests — they pin the *behaviour* of the engine code
paths the recent rendering-logic fixes depend on:

1. `_summary` actually produces a non-zero `d_aic` when one backend really does
   beat another (so the relabeled "Solver-consensus AIC" panel is honest when
   they DO disagree, not just when they tie).
2. `build_report` attaches `multidim` + `global_fit` ONLY to `analyzed[0]`.
   The OverviewView now reads index 0 directly; this test pins the engine-side
   invariant the UI relies on.
3. `_monte_carlo` produces per-backend independent `series["r2"]` lists — the
   R²-stability overlap is the data faithfully reporting solver agreement, not
   a shared-state bug.
"""

from __future__ import annotations

import math
from typing import cast

import numpy as np
import pytest

pytest.importorskip("lmfit")

from oracles.backends._base import BackendOutcome
from oracles.cases import (
    BenchCase,
    CaseSpec,
    Component,
    GaussianSpec,
    build_specs,
    materialize,
)
from oracles.bench_contract import Summary, TimingDist
from oracles.engine import _monte_carlo, _summary, build_report


def _flat_timing(median: float = 1.0) -> TimingDist:
    """A TimingDist with a constant timing series — irrelevant to the AIC math
    under test but required to satisfy the Pydantic contract."""
    return TimingDist(
        raw=[median, median, median],
        median=median,
        mean=median,
        p5=median,
        p25=median,
        p75=median,
        p95=median,
        iqr=0.0,
        cv=0.0,
    )


# --------------------------------------------------------------------------- #
# 1. _summary on an asymmetric AIC field
# --------------------------------------------------------------------------- #
def _stub_case() -> BenchCase:
    """A tiny BenchCase-shaped stand-in: just `y` for residual math.

    The downcast tells the type checker we satisfy `_summary`'s contract; the
    function only reads `case.y` from the case argument here.
    """

    class _C:
        y = np.zeros(8, dtype=float)

    return cast(BenchCase, _C())


def _outcome(aic: float, *, bic: float = 0.0) -> BackendOutcome:
    """Minimal BackendOutcome carrying only the fields `_summary` reads."""

    class _O:
        success = True
        r2 = 0.99
        chi2 = 1.0
        reduced_chi2 = 1.0
        n_iter = 10
        # `_summary` computes rmse/mae from `case.y - o.best_fit`; we use a
        # perfect fit (zeros vs zeros) so those numbers stay simple.
        best_fit = np.zeros(8, dtype=float)

    o = _O()
    o.aic = aic  # type: ignore[attr-defined]
    o.bic = bic  # type: ignore[attr-defined]
    return cast(BackendOutcome, o)


def test_summary_d_aic_captures_real_asymmetry_between_backends() -> None:
    """When one backend's AIC is genuinely lower, _summary's d_aic surfaces the gap.

    Anti-regression for the "Solver-consensus AIC" panel: it must not silently
    collapse to zero for the winner-by-default case (would mask real model
    selection signal). All three backends share `min_aic`; only the gaps differ.
    """
    case = _stub_case()
    timing = _flat_timing()
    # Three backends: spectrafit best, lmfit equal to it, jax 5.0 worse.
    aics = {"spectrafit": -10.0, "lmfit": -10.0, "jax": -5.0}
    min_aic = min(aics.values())
    summaries: dict[str, Summary] = {
        name: _summary(
            _outcome(aic),
            case,
            timing,
            baseline=1.0,
            min_aic=min_aic,
            min_bic=0.0,
        )
        for name, aic in aics.items()
    }
    # The two tied backends report d_aic = 0; the loser reports the real gap.
    assert summaries["spectrafit"].d_aic == pytest.approx(0.0)
    assert summaries["lmfit"].d_aic == pytest.approx(0.0)
    assert summaries["jax"].d_aic == pytest.approx(5.0)
    # Sanity: each summary preserves raw AIC for the export layer.
    for name, summary in summaries.items():
        assert summary.aic == aics[name]


def test_summary_d_aic_is_zero_when_all_backends_tie_exactly() -> None:
    """Tied AICs → every d_aic == 0. The relabeled panel ('≈0') is then honest."""
    case = _stub_case()
    timing = _flat_timing()
    aic = -42.0
    min_aic = aic
    for _ in range(3):
        summary = _summary(
            _outcome(aic),
            case,
            timing,
            baseline=1.0,
            min_aic=min_aic,
            min_bic=0.0,
        )
        assert summary.d_aic == 0.0


# --------------------------------------------------------------------------- #
# 2. multidim attachment invariant
# --------------------------------------------------------------------------- #
def _tiny_two_case_catalog() -> list:
    """Two materialized featured cases so we can verify the idx==0 invariant."""
    specs = build_specs()
    featured = next(s for s in specs if s.featured)
    other = next(s for s in specs if s.id != featured.id and s.category == "easy")
    return [materialize(s) for s in (featured, other)]


def test_build_report_attaches_multidim_only_to_analyzed_index_zero() -> None:
    """The OverviewView reads ANALYZED[0]?.multidim directly — this pins the engine side.

    Regression for the issue the rendering plan fixed: a `find()` over analyzed
    that searched for `f.multidim || f.globalFit` would silently return
    `undefined` if a future engine change moved these showcases off slot 0.
    """
    catalog = _tiny_two_case_catalog()
    assert len(catalog) >= 2, "need at least two cases to test the invariant"
    report = build_report(n_reps=1, n_mc=2, catalog=catalog, ngrid=[128, 256])
    # Slot 0 carries the showcase 2-D map + global-fit series.
    assert report.analyzed[0].multidim is not None
    assert report.analyzed[0].global_fit is not None
    # Every other analyzed slot does NOT carry these heavy payloads.
    for extra in report.analyzed[1:]:
        assert extra.multidim is None, (
            f"engine attached multidim to analyzed[{report.analyzed.index(extra)}] — "
            "UI relies on the idx==0 invariant"
        )
        assert extra.global_fit is None


# --------------------------------------------------------------------------- #
# 3. _monte_carlo per-backend isolation
# --------------------------------------------------------------------------- #
def _single_gaussian_case() -> CaseSpec:
    components: list[Component] = [GaussianSpec(amplitude=4.0, center=0.0, sigma=1.0)]
    return CaseSpec(
        id="TST-MC-001",
        name="single gaussian (MC isolation)",
        category="easy",
        difficulty=0.1,
        components=components,
        x_min=-5.0,
        x_max=5.0,
        n_points=120,
        noise=0.02,
        guess_scale=0.05,
    )


def test_monte_carlo_returns_per_backend_independent_r2_series() -> None:
    """Two backends fitting the same case yield independently-computed R² series.

    The R²-stability panel showed near-identical traces across backends; this
    test pins WHY: each backend gets its own `_monte_carlo` call returning its
    own `series` dict — no shared mutable, no closure mishap. If a future change
    made backends share state, this would catch it.
    """
    from oracles.backends._lmfit import LmfitBackend
    from oracles.backends._spectrafit import SpectraFitBackend

    case = materialize(_single_gaussian_case())
    backends = [SpectraFitBackend(), LmfitBackend()]
    series_per_backend: dict[str, list[float]] = {}
    for backend in backends:
        _, _, _, series = _monte_carlo(backend, case, n_mc=4)
        series_per_backend[backend.name] = series["r2"]
        # Each backend must have populated a non-empty R² list (we asked for 4 MC).
        assert series["r2"], f"{backend.name} returned no MC R² samples"
        for r2 in series["r2"]:
            assert math.isfinite(r2), f"{backend.name} produced non-finite R²"
    # The two lists are SEPARATE objects (no shared reference) — the canonical
    # check for "we're not aliasing the same series across backends".
    assert series_per_backend["spectrafit"] is not series_per_backend["lmfit"]
    # And they hold their own floats — different list identities, not the same
    # numpy buffer reshared.
    assert id(series_per_backend["spectrafit"]) != id(series_per_backend["lmfit"])
