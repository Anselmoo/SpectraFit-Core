r"""``success=True`` from the faer LM-family solvers implies a stationary endpoint (#93).

A fit that reports ``success=True`` claims that a convergence test fired at a
local minimum. This test checks that claim from outside the solver, on a measured
spectrum: the Fe $L_{2,3}$ edge of Fe$_2$O$_3$ (EELS Data Base, ODbL; licence and
attribution in ``reproducibility/spectra/eelsdb-fe2o3-l23/README.md``) between
700 and 735 eV, fitted with a constant background, two arctangent edge steps and
nine Gaussian white lines, with the bounds of the EELS solver cross-check. The
``constrained`` model adds the four expression edges of that cross-check (the
$L_2$ step is half the $L_3$ step, both steps share one width, each step sits at
the centre of its main white line).

Stationarity is measured as in the cross-check. Let $\theta$ be the free
parameters at the endpoint, $r = y - f(\theta)$ the residual and
$\mathrm{RSS} = \lVert r \rVert^2$. $J$ is the central-difference Jacobian of $f$
with step $h_i = 6.06 \times 10^{-6} s_i$, $s_i = \max(|\theta_i|, 10^{-3})$,
its columns scaled by $s_i$. A component at an active bound (within $10^{-4}$ of
the bound span) whose gradient points out of the feasible set is held and its
column removed. With $\delta = \arg\min_d \lVert J d - r \rVert$ the Gauss-Newton
step, the predicted decrease relative to the residual sum of squares is

$$
g_{\mathrm{GN}} = \frac{\lVert J \delta \rVert^2}{\mathrm{RSS}}
= \frac{\lVert P_J r \rVert^2}{\mathrm{RSS}},
$$

and an endpoint is stationary when $g_{\mathrm{GN}} \le 10^{-6}$.

The cases are five fixed starts of the cross-check (the seeded starts are read
from ``eels_crosscheck_starts.json`` next to this file; ``default`` is the default
guess) for each of ``lm``, ``trf`` and ``geodesic``, which share the faer LM core.
In the cross-check (wheel 0.1.2, ``lm``) every one of the four seeded starts
ended with ``success=True`` and $g_{\mathrm{GN}}$ between $3 \times 10^{-3}$ and
$0.81$; ``multistart_29`` (constrained) is one of the five soft stops upgraded to
success by the $r^2 \ge 0.9$ rule. The termination changes of #93 (the
stationarity gate on ``success``) make the test pass: every ``success=True``
endpoint is stationary, and the fits that stop at a non-stationary point report
``success=False``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from spectrafit_core import (
    FitOptions,
    MeasurementData,
    arctan_step,
    compose,
    constant,
    fit,
    gaussian,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECTRUM = REPO_ROOT / "reproducibility" / "spectra" / "eelsdb-fe2o3-l23" / "DspecTi3wqG.msa"
SPECTRUM_SHA256 = "28e88f85350c353f524c828740c533312dc897505410ac940cd544060df963d4"
STARTS = Path(__file__).with_name("eels_crosscheck_starts.json")
WINDOW_EV = (700.0, 735.0)

SOLVERS = ("lm", "trf", "geodesic")
# (model, start). Termination reason and GN decrease of the cross-check (lm) in the comment.
CASES = (
    ("free", "multistart_0"),  # converged_xtol, 0.69
    ("free", "multistart_3"),  # converged_ftol, 0.69
    ("free", "default"),  # converged_ftol, 0.053
    ("constrained", "multistart_25"),  # converged_xtol, 0.0029
    ("constrained", "multistart_29"),  # no_improvement_possible upgraded at r^2 0.9128, 0.81
)

GN_TOL = 1e-6  # stationary: Gauss-Newton predicted decrease / RSS <= this
H_REL, THETA_FLOOR = 6.06e-6, 1e-3  # central-difference step, relative to max(|theta|, floor)
AT_BOUND_REL = 1e-4  # active bound, relative to the bound span

# (node id, centre, height, width) starting values and the bound rule of the cross-check.
L3_LINES = (
    ("l3_a", 708.9, 4000.0, 0.4),
    ("l3_b", 709.3, 15000.0, 0.4),
    ("l3_c", 710.8, 28000.0, 0.6),
    ("l3_d", 712.2, 9000.0, 0.9),
    ("l3_e", 713.8, 5000.0, 1.2),
    ("l3_s", 716.5, 1500.0, 2.0),
)
L2_LINES = (
    ("l2_a", 722.3, 4000.0, 0.6),
    ("l2_b", 723.8, 4000.0, 0.9),
    ("l2_c", 725.2, 2000.0, 1.2),
)
# target <- (expression, the same relation evaluated on a parameter dict)
TIES = {
    "step_l2.amplitude": ("step_l3.amplitude / 2", lambda p: p["step_l3.amplitude"] / 2),
    "step_l2.sigma": ("step_l3.sigma", lambda p: p["step_l3.sigma"]),
    "step_l3.center": ("l3_c.center", lambda p: p["l3_c.center"]),
    "step_l2.center": ("l2_b.center", lambda p: p["l2_b.center"]),
}
INF = float("inf")
# Node factory by node id; every other node is a Gaussian white line.
FACTORIES = {"bg": constant, "step_l3": arctan_step, "step_l2": arctan_step}


def _param_table() -> list[tuple[str, float, float, float]]:
    """(key, default start, lower, upper) in node order; an open side is ``inf``."""
    rows = [
        ("bg.c", 5700.0, 0.0, INF),
        ("step_l3.amplitude", 1900.0, 0.0, INF),
        ("step_l3.center", 710.0, 705.0, 715.0),
        ("step_l3.sigma", 0.6, 0.3, 5.0),
        ("step_l2.amplitude", 950.0, 0.0, INF),
        ("step_l2.center", 723.0, 718.0, 728.0),
        ("step_l2.sigma", 0.6, 0.3, 5.0),
    ]
    for node_id, centre, height, width in L3_LINES + L2_LINES:
        rows += [
            (f"{node_id}.amplitude", height, 0.0, INF),
            (f"{node_id}.center", centre, centre - 1.2, centre + 1.2),
            (f"{node_id}.sigma", width, 0.1, 4.0),
        ]
    return rows


TABLE = _param_table()
KEYS = [key for key, *_ in TABLE]
DEFAULT = {key: default for key, default, _, _ in TABLE}
LOWER = {key: lower for key, _, lower, _ in TABLE}
UPPER = {key: upper for key, _, _, upper in TABLE}


def _read_window() -> tuple[np.ndarray, np.ndarray]:
    raw = SPECTRUM.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SPECTRUM_SHA256:
        # Not an AssertionError: the strict xfail must not absorb a changed input.
        raise ValueError(f"EELS spectrum changed: {SPECTRUM}")
    rows = [
        line.split(",", 1)
        for line in raw.decode("latin-1").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    x = np.array([float(a) for a, _ in rows])
    y = np.array([float(b) for _, b in rows])
    keep = (x >= WINDOW_EV[0]) & (x <= WINDOW_EV[1])
    return x[keep], y[keep]


def _full(values: dict[str, float], tied: dict) -> dict[str, float]:
    """All parameters, the tied ones recomputed from their expressions."""
    p = {key: float(values[key]) for key in KEYS}
    for target, (_, relation) in tied.items():
        p[target] = relation(p)
    return p


def _graph(start: dict[str, float], tied: dict):
    nodes = []
    for node_id in dict.fromkeys(key.split(".", 1)[0] for key in KEYS):
        factory = FACTORIES.get(node_id, gaussian)
        kwargs: dict[str, float] = {}
        for key in (k for k in KEYS if k.startswith(f"{node_id}.")):
            name = key.split(".", 1)[1]
            kwargs[name] = start[key]
            if np.isfinite(LOWER[key]):
                kwargs[f"{name}_min"] = LOWER[key]
            if np.isfinite(UPPER[key]):
                kwargs[f"{name}_max"] = UPPER[key]
        nodes.append(factory(node_id, **kwargs))
    builder = compose(nodes)
    for target, (expression, _) in tied.items():
        builder = builder.bind(expression, to=target)
    return builder.build()


def _model(x: np.ndarray, p: dict[str, float]) -> np.ndarray:
    """The fitted model in numpy, independent of the library under test."""
    out = np.full_like(x, p["bg.c"])
    for step in ("step_l3", "step_l2"):
        z = (x - p[f"{step}.center"]) / p[f"{step}.sigma"]
        out = out + p[f"{step}.amplitude"] * (0.5 + np.arctan(z) / np.pi)
    for node_id, *_ in L3_LINES + L2_LINES:
        z = (x - p[f"{node_id}.center"]) / p[f"{node_id}.sigma"]
        out = out + p[f"{node_id}.amplitude"] * np.exp(-0.5 * z**2)
    return out


def _active(p: dict[str, float], free: list[str]) -> dict[str, str]:
    out = {}
    for key in free:
        lower, upper = LOWER[key], UPPER[key]
        two_sided = np.isfinite(lower) and np.isfinite(upper)
        tol = AT_BOUND_REL * ((upper - lower) if two_sided else max(abs(DEFAULT[key]), 1.0))
        out[key] = "lower" if p[key] - lower <= tol else "upper" if upper - p[key] <= tol else ""
    return {key: side for key, side in out.items() if side}


def gn_decrease_rel(x: np.ndarray, y: np.ndarray, p: dict[str, float], tied: dict) -> float:
    r"""Gauss-Newton predicted decrease $\lVert P_J r \rVert^2 / \mathrm{RSS}$ at ``p``."""
    free = [key for key in KEYS if key not in tied]
    theta = np.array([p[key] for key in free])
    scale = np.maximum(np.abs(theta), THETA_FLOOR)
    h = H_REL * scale

    def at(t: np.ndarray) -> dict[str, float]:
        return _full(dict(p) | dict(zip(free, map(float, t), strict=True)), tied)

    r = y - _model(x, p)
    rss = float(r @ r)
    jac = np.empty((y.size, theta.size))
    for i in range(theta.size):
        up, down = theta.copy(), theta.copy()
        up[i] += h[i]
        down[i] -= h[i]
        jac[:, i] = (_model(x, at(up)) - _model(x, at(down))) / (2.0 * h[i])
    grad = -2.0 * jac.T @ r
    active = _active(p, free)
    held = np.array(
        [
            (active.get(key) == "lower" and grad[i] > 0)
            or (active.get(key) == "upper" and grad[i] < 0)
            for i, key in enumerate(free)
        ],
        dtype=bool,
    )
    js = jac[:, ~held] * scale[~held]
    step, *_ = np.linalg.lstsq(js, r, rcond=None)
    return float(np.sum((js @ step) ** 2) / rss)


def test_lm_success_implies_stationary() -> None:
    x, y = _read_window()
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    seeded = json.loads(STARTS.read_text())["starts"]
    starts = seeded | {"default": DEFAULT}

    violations, n_success = [], 0
    for solver in SOLVERS:
        options = FitOptions(solver=solver)
        for model, label in CASES:
            tied = TIES if model == "constrained" else {}
            result = fit(_graph(_full(starts[label], tied), tied), data, options)
            if not result.success:
                continue
            n_success += 1
            p = {key: float(result.parameters[key].value) for key in KEYS}
            finite = all(np.isfinite(v) for v in p.values())
            gn = gn_decrease_rel(x, y, p, tied) if finite else float("nan")
            if not gn <= GN_TOL:
                violations.append(f"{solver} {model}/{label}: {result.message}, GN {gn:.3g}")

    assert not violations, (
        f"{len(violations)} of {n_success} success=True endpoints are not stationary "
        f"(GN predicted decrease / RSS > {GN_TOL:g}):\n  " + "\n  ".join(violations)
    )
