r"""``success=True`` implies a stationary endpoint on a five-parameter model with a width at its bound (#108).

The reproducer of #108: one Gaussian on a linear background, 201 points on
$[0, 20]$, $f(x) = 50 \exp(-\tfrac{1}{2}(x - 10)^2) + 0.1 x + 2$, noise
$\sigma_k = 0.2 + 0.01 f(x_k)$ drawn from ``numpy.random.default_rng([7, seed])``
for the 40 seeds $0, \dots, 39$. The fit starts from amplitude 59.404
($\ge 0$), centre 9.0794, width 2.8017 ($\ge 1.5$), slope 0.1 and intercept 2,
weighted by $1/\sigma_k$, with ``solver="trf"``. The width ends at its lower
bound of 1.5. With wheel 0.1.2 every seed reported ``success=True`` at an
endpoint that a further polish improved by 78 to 2910 in weighted $\chi^2$.

Stationarity is measured as in ``test_lm_success_implies_stationary.py``, on the
weighted residual $r_k = (y_k - f(\theta; x_k)) / \sigma_k$ with
$\mathrm{RSS} = \lVert r \rVert^2$. $J$ is the central-difference Jacobian of the
weighted model with step $h_i = 6.06 \times 10^{-6} s_i$,
$s_i = \max(|\theta_i|, 10^{-3})$, its columns scaled by $s_i$. A component at an
active bound (within $10^{-4} \max(|\theta^{(0)}_i|, 1)$ of a one-sided bound)
whose gradient points out of the feasible set is held and its column removed.
With $\delta = \arg\min_d \lVert J d - r \rVert$,

$$
g_{\mathrm{GN}} = \frac{\lVert J \delta \rVert^2}{\mathrm{RSS}},
$$

and an endpoint is stationary when $g_{\mathrm{GN}} \le 10^{-6}$. The test passes
when no seed reports ``success=True`` at an endpoint with
$g_{\mathrm{GN}} > 10^{-6}$.
"""

from __future__ import annotations

import numpy as np
import spectrafit_core as sfc

SEEDS = range(40)
GN_TOL = 1e-6  # stationary: Gauss-Newton predicted decrease / RSS <= this
H_REL, THETA_FLOOR = 6.06e-6, 1e-3  # central-difference step, relative to max(|theta|, floor)
AT_BOUND_REL = 1e-4  # active one-sided bound, relative to max(|start|, 1)
MODEL_AGREEMENT = 1e-9  # independent model against best_fit, relative to max |best_fit|

KEYS = ("g.amplitude", "g.center", "g.sigma", "bg.slope", "bg.intercept")
START = {
    "g.amplitude": 59.404,
    "g.center": 9.0794,
    "g.sigma": 2.8017,
    "bg.slope": 0.1,
    "bg.intercept": 2.0,
}
LOWER = {"g.amplitude": 0.0, "g.sigma": 1.5}


def _data(seed: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    x = np.linspace(0.0, 20.0, 201)
    f = 50.0 * np.exp(-0.5 * ((x - 10.0) / 1.0) ** 2) + 0.1 * x + 2.0
    sig = 0.2 + 0.01 * f
    rng = np.random.default_rng([7, seed])
    return x, f + sig * rng.standard_normal(201), sig


def _graph() -> sfc.FitGraph:
    p, node, kind = sfc.Parameter, sfc.ModelNodeSpec, sfc.ModelType
    return sfc.FitGraph(
        nodes=[
            node(
                id="g",
                model_type=kind.GAUSSIAN,
                parameters={
                    "amplitude": p(value=START["g.amplitude"], min=LOWER["g.amplitude"]),
                    "center": p(value=START["g.center"]),
                    "sigma": p(value=START["g.sigma"], min=LOWER["g.sigma"]),
                },
            ),
            node(
                id="bg",
                model_type=kind.LINEAR,
                parameters={
                    "slope": p(value=START["bg.slope"]),
                    "intercept": p(value=START["bg.intercept"]),
                },
            ),
        ],
    )


def _model(x: np.ndarray, theta: np.ndarray) -> np.ndarray:
    """The fitted model in numpy, independent of the library under test."""
    amplitude, center, sigma, slope, intercept = theta
    return amplitude * np.exp(-0.5 * ((x - center) / sigma) ** 2) + slope * x + intercept


def gn_decrease_rel(x: np.ndarray, y: np.ndarray, sig: np.ndarray, theta: np.ndarray) -> float:
    r"""Gauss-Newton predicted decrease $\lVert P_J r \rVert^2 / \mathrm{RSS}$ at ``theta``."""
    r = (y - _model(x, theta)) / sig
    scale = np.maximum(np.abs(theta), THETA_FLOOR)
    h = H_REL * scale
    jac = np.empty((y.size, theta.size))
    for i in range(theta.size):
        up, down = theta.copy(), theta.copy()
        up[i] += h[i]
        down[i] -= h[i]
        jac[:, i] = (_model(x, up) - _model(x, down)) / (2.0 * h[i] * sig)
    grad = -2.0 * jac.T @ r
    held = np.array(
        [
            key in LOWER
            and theta[i] - LOWER[key] <= AT_BOUND_REL * max(abs(START[key]), 1.0)
            and grad[i] > 0
            for i, key in enumerate(KEYS)
        ],
        dtype=bool,
    )
    js = jac[:, ~held] * scale[~held]
    step, *_ = np.linalg.lstsq(js, r, rcond=None)
    return float(np.sum((js @ step) ** 2) / float(r @ r))


def test_issue108_success_implies_stationary() -> None:
    graph, options = _graph(), sfc.FitOptions(solver="trf")
    violations, n_success = [], 0
    for seed in SEEDS:
        x, y, sig = _data(seed)
        data = sfc.MeasurementData(x=x.tolist(), y=y.tolist(), sigma=sig.tolist())
        result = sfc.fit(graph, data, options)
        theta = np.array([float(result.parameters[key].value) for key in KEYS])
        best_fit = np.asarray(result.best_fit, dtype=float)
        assert np.max(np.abs(_model(x, theta) - best_fit)) <= MODEL_AGREEMENT * np.max(
            np.abs(best_fit),
        ), f"seed {seed}: the numpy model does not reproduce best_fit"
        if not result.success:
            continue
        n_success += 1
        gn = gn_decrease_rel(x, y, sig, theta) if np.all(np.isfinite(theta)) else float("nan")
        if not gn <= GN_TOL:
            violations.append(f"seed {seed}: {result.message}, sigma {theta[2]:.6g}, GN {gn:.3g}")

    assert not violations, (
        f"{len(violations)} of {n_success} success=True endpoints are not stationary "
        f"(GN predicted decrease / RSS > {GN_TOL:g}):\n  " + "\n  ".join(violations)
    )
