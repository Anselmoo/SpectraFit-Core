"""Regression: on a well-posed case, all backends produce nearly-identical AIC.

The HTML report's "Solver-consensus AIC" panel surfaces ``Summary.dAIC`` per
backend, computed by ``engine._summary`` as ``o.aic − min_aic``. The framing
("near-zero ΔAIC means all solvers converged to the same minimum") only stays
honest if the engine actually produces AIC values that agree across backends
when the optimization problem is well-posed. A future change that introduces a
solver-specific bias (e.g. a backend reporting chi² from a different point in
the iteration) would silently invalidate the panel.

This test pins the invariant against a tiny scaling-style case (one Gaussian,
clean data) where every supported backend must reach essentially the same fit.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("lmfit")

from oracles.backends import get_backends
from oracles.cases import CaseSpec, Component, GaussianSpec, materialize
from oracles.engine import _safe_fit


def _clean_gaussian_case() -> CaseSpec:
    """One Gaussian, low noise, dense grid — every solver should land on the same fit."""
    components: list[Component] = [
        GaussianSpec(amplitude=4.0, center=0.0, sigma=1.0),
    ]
    return CaseSpec(
        id="TST-AIC-001",
        name="single gaussian (AIC parity)",
        category="easy",
        difficulty=0.1,
        components=components,
        x_min=-5.0,
        x_max=5.0,
        n_points=240,
        noise=0.01,
        guess_scale=0.05,
    )


def test_all_backends_aic_agree_on_well_posed_case() -> None:
    """All backends' Summary.aic must agree within 1e-3 on a clean Gaussian fit.

    Proves the panel's framing — "all near-zero means consensus" — is honest:
    if a backend silently reported a different chi² provenance, dAIC would
    widen here and this test would catch it.
    """
    case = materialize(_clean_gaussian_case())
    backends = get_backends()
    aics: dict[str, float] = {}
    for backend in backends:
        outcome = _safe_fit(backend, case, n_reps=1)
        if outcome is None:
            continue  # backend skipped this case (e.g. jax unavailable)
        assert math.isfinite(outcome.aic), f"{backend.name}.aic must be finite"
        aics[backend.name] = outcome.aic
    # The test is meaningful only with at least two backends in agreement.
    assert len(aics) >= 2, f"need ≥ 2 backends for parity; ran {list(aics)}"
    spread = max(aics.values()) - min(aics.values())
    assert spread < 1e-3, (
        f"AIC spread {spread:.3e} across backends {aics} — "
        "the 'consensus AIC' panel framing assumes solvers converge to the same minimum"
    )
