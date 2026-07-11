"""W2d — solver-output oracle (Invariant V, V3).

The canonical audit test behind wire W2d: spectrafit's *solver output* (fitted
parameters AND the covariance-derived per-parameter σ) is verified against an
independent LM implementation — ``scipy.optimize.least_squares`` (method='lm') —
on the same data. This is the end-to-end value check the wire matrix lacked:
kernel ``eval`` parity proves the model formula, but only this proves the *solve*
(parameters + uncertainty) is correct against an external reference.

``wire_w2d_solver_output_oracle`` reads this test's pass/fail state via the
pytest lastfailed cache (the same mechanism as W1/W3/W4/W6).
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares

from spectrafit_core import (
    FitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)


def _gauss(x: np.ndarray, amplitude: float, center: float, sigma: float) -> np.ndarray:
    return amplitude * np.exp(-0.5 * ((x - center) / sigma) ** 2)


def _scipy_stderr(result: object, n_data: int, n_params: int) -> np.ndarray:
    """Parameter 1σ from a scipy OptimizeResult (SVD pseudo-inverse of J, scaled
    by 2·cost/(m−n) — the same construction scipy.optimize.curve_fit uses)."""
    jac = np.asarray(result.jac, dtype=float)  # ty: ignore[unresolved-attribute]
    _u, sv, vh = np.linalg.svd(jac, full_matrices=False)
    del _u
    threshold = np.finfo(float).eps * max(jac.shape) * sv[0]
    sv_inv = np.where(sv > threshold, 1.0 / np.where(sv > 0, sv, 1.0), 0.0)
    cov = (vh.T * sv_inv**2) @ vh
    # scipy sets result.cost = ½‖r‖², so 2·cost = ‖r‖² = χ²; s_sq = χ²/dof is the
    # same residual-scale spectrafit's no-σ covariance path uses (postfit.rs).
    s_sq = 2.0 * float(result.cost) / max(n_data - n_params, 1)  # ty: ignore[unresolved-attribute]
    return np.sqrt(np.maximum(np.diag(cov) * s_sq, 0.0))


def test_audit_solver_output_oracle() -> None:
    """spectrafit params + covariance σ agree with scipy.optimize.least_squares."""
    rng = np.random.default_rng(2026)
    x = np.linspace(-4.0, 4.0, 160)
    truth = (3.0, 0.3, 0.8)  # amplitude, center, sigma
    y = _gauss(x, *truth) + rng.normal(0.0, 0.03, x.size)

    # --- spectrafit ---
    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=1.0, min=0.0),
                    "center": Parameter(value=0.0),
                    "sigma": Parameter(value=1.0, min=1e-6),
                },
            )
        ]
    )
    sf = fit(graph, MeasurementData(x=x.tolist(), y=y.tolist()))
    assert sf.success

    # --- scipy (independent LM oracle) ---
    def _resid(p: np.ndarray) -> np.ndarray:
        return _gauss(x, p[0], p[1], p[2]) - y

    sc = least_squares(_resid, [1.0, 0.0, 1.0], method="lm")
    assert sc.success

    labels = ["amplitude", "center", "sigma"]
    sf_vals = [sf.params[f"peak.{name}"].value for name in labels]

    # Parameters agree between the two independent MINPACK callers.
    for name, a, b in zip(labels, sf_vals, sc.x):
        rel = abs(a - b) / max(abs(b), 1e-9)
        assert rel < 1e-4, f"param {name}: spectrafit={a:.8g} scipy={b:.8g} rel={rel:.2e}"

    # Covariance-derived σ agree (looser — different covariance normalisation).
    sc_se = _scipy_stderr(sc, n_data=x.size, n_params=3)
    for name, se in zip(labels, sc_se):
        sf_se = sf.params[f"peak.{name}"].stderr
        assert sf_se is not None, f"spectrafit σ for {name} is None"
        assert se > 0.0
        rel = abs(sf_se - se) / se
        assert rel < 0.10, f"σ {name}: spectrafit={sf_se:.4g} scipy={se:.4g} rel={rel:.2e}"
