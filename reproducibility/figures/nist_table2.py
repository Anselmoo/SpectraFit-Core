r"""Generate the paper's NIST StRD agreement table (Table 2) for all 22 datasets.

Table 2 reports, per dataset, the log-relative error (LRE) of the least
accurately recovered parameter -- the significant figures of agreement with
NIST's certified values on each dataset's *worst* parameter -- for four solvers,
plus the same measure applied to spectrafit-core's fitted standard errors
against NIST's certified standard deviations.

Columns:

* ``spectrafit_core`` -- spectrafit-core's LM solver.
* ``sigma``           -- the LRE measure on spectrafit-core's fitted standard
  errors versus NIST's certified standard deviations.
* ``lmfit``           -- ``lmfit.minimize(method="leastsq")``.
* ``scipy_lm``        -- ``scipy.optimize.least_squares(method="lm")``.
* ``scipy_trf``       -- ``scipy.optimize.least_squares(method="trf")``.

Three deliberate choices:

* Every backend runs from NIST's **Start 2** -- the same guess the shipped audit
  (``oracles.audit.nist``) and the scenario tests fit from. ``--start START1``
  writes the same table from Start 1 (``nist_table2_start1.json``); ``--start
  both`` writes the per-start detail (``nist_table2_both.json``): for every
  dataset, start and implementation the least accurately recovered parameter and
  standard error (named), the LRE of the residual sum of squares against NIST's
  certified value, the success flag and the termination reason, plus one summary
  line per start and implementation (worst parameter LRE and its dataset, and the
  datasets that did not converge). The comparators' standard errors use the
  ``curve_fit`` covariance of the final Jacobian (lmfit reports its own).
* Every backend gets the tolerance the shipped audit uses (1e-12), not a tighter
  one chosen here. Quoting a comparison at a tolerance the software does not
  actually run at would describe a configuration nobody ships. This matches
  ``nist_head_to_head.py``, whose lmfit column this generator reproduces exactly.
* Where a measure genuinely does not apply, the JSON carries ``null`` plus a
  machine-readable reason rather than a number. Two datasets need this: NIST's
  parameterization is a *nonlinear* function of the fitted parameters on
  Eckerle4 ($b_1 = A \cdot \sigma$) and DanWood ($b_2 = -1/s$), so a fitted
  standard error does not propagate through the projection by a constant factor
  and no honest sigma LRE exists for them.

The dataset roster, the model graphs and the NIST-parameterization projections
are read from ``oracles.audit.nist._RECIPES`` -- the audit's own registry -- so
this table cannot drift from the shipped audit. The reference model callables and
the LRE helper are reused from ``nist_head_to_head.py`` in this directory for the
same reason.

Run:  uv run python reproducibility/figures/nist_table2.py [--start START1|START2|both]
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import platform
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from importlib import import_module
from pathlib import Path
from typing import Any, Literal

import lmfit
import numpy as np
import scipy
from nist_head_to_head import MODELS, lre
from oracles.audit.nist import _RECIPES, SQRT2
from pydantic import BaseModel, ConfigDict
from scipy.optimize import least_squares
from spectrafit_core import FitOptions, MeasurementData, fit

OUT = Path(__file__).with_name("nist_table2.json")
TOL = 1e-12
"""Stopping tolerance for every backend.

The shipped default is the tolerance the audit itself runs at, not a tighter one
chosen for the paper -- quoting a comparison at a tolerance the software does not
actually run at would describe a configuration nobody ships.

`--tolerance` exists so the paper can say what changes at a tighter one and have
the reader check it. The paper states that moving to 1e-15 raises several
comparator cells while spectrafit-core's do not; that claim needs a committed
artifact to rest on, so the 1e-15 run is regenerated and shipped beside this one
rather than quoted from a measurement nobody can repeat.
"""
MAX_IT = 10_000
START = "START2"
StartName = Literal["START1", "START2"]
STARTS: tuple[StartName, ...] = ("START1", "START2")
START_LABELS: dict[str, str] = {"START1": "Start 1", "START2": "Start 2"}
IMPLEMENTATIONS: tuple[str, ...] = ("spectrafit_core", "lmfit", "scipy_lm", "scipy_trf")
"""The implementations of the per-start detail output (``--start both``)."""

_DIFFICULTY_MARK = "difficulty"
_CLASSIFIES = "NIST classifies "

# --- Standard-error projection -------------------------------------------------
#
# ``_RECIPES`` fits spectrafit's own parameterization and projects the result
# back to NIST's b1..bk. A fitted standard error only survives that projection
# when the projection is linear in a single fitted parameter, in which case it
# scales by |coefficient|. These maps name the fitted parameter and the
# coefficient behind every NIST parameter, mirroring the audit's ``_project_*``
# helpers one-for-one; ``main`` re-derives each projected value from the map and
# fails loudly if it ever disagrees with the audit's own projection.

_TWO_GAUSSIAN: dict[str, tuple[str, float]] = {
    "b1": ("exp.A1", 1.0),
    "b2": ("exp.lam1", 1.0),
    "b3": ("g1.amplitude", 1.0),
    "b4": ("g1.center", 1.0),
    "b5": ("g1.sigma", SQRT2),
    "b6": ("g2.amplitude", 1.0),
    "b7": ("g2.center", 1.0),
    "b8": ("g2.sigma", SQRT2),
}
_LANCZOS: dict[str, tuple[str, float]] = {
    "b1": ("exp12.A1", 1.0),
    "b2": ("exp12.lam1", 1.0),
    "b3": ("exp12.A2", 1.0),
    "b4": ("exp12.lam2", 1.0),
    "b5": ("exp3.A1", 1.0),
    "b6": ("exp3.lam1", 1.0),
}
_BOXBOD: dict[str, tuple[str, float]] = {"b1": ("bod.amplitude", 1.0), "b2": ("bod.rate", 1.0)}
_MISRA1A: dict[str, tuple[str, float]] = {"b1": ("m1a.amplitude", 1.0), "b2": ("m1a.rate", 1.0)}
_MISRA1B: dict[str, tuple[str, float]] = {"b1": ("m1b.amplitude", 1.0), "b2": ("m1b.rate", 1.0)}
_MGH17: dict[str, tuple[str, float]] = {
    "b1": ("bg.c", 1.0),
    "b2": ("exp.A1", 1.0),
    "b3": ("exp.A2", 1.0),
    "b4": ("exp.lam1", 1.0),
    "b5": ("exp.lam2", 1.0),
}
_MGH09: dict[str, tuple[str, float]] = {
    "b1": ("mgh09.amplitude", 1.0),
    "b2": ("mgh09.num_lin", 1.0),
    "b3": ("mgh09.den_lin", 1.0),
    "b4": ("mgh09.den_const", 1.0),
}
_BENNETT5: dict[str, tuple[str, float]] = {
    "b1": ("b5.amplitude", 1.0),
    "b2": ("b5.offset", 1.0),
    "b3": ("b5.shape", 1.0),
}
_ECKERLE4: dict[str, tuple[str, float]] = {"b2": ("g.sigma", 1.0), "b3": ("g.center", 1.0)}
_ROSZMAN1: dict[str, tuple[str, float]] = {
    "b1": ("lin.intercept", 1.0),
    "b2": ("lin.slope", -1.0),
    "b3": ("atan.sigma", 1.0),
    "b4": ("atan.center", 1.0),
}
_DANWOOD: dict[str, tuple[str, float]] = {"b1": ("pw.amplitude", 1.0)}
_RATIONAL_QUADRATIC: dict[str, tuple[str, float]] = {
    "b1": ("rat.a0", 1.0),
    "b2": ("rat.a1", 1.0),
    "b3": ("rat.a2", 1.0),
    "b4": ("rat.b1", 1.0),
    "b5": ("rat.b2", 1.0),
}
_RATIONAL_CUBIC: dict[str, tuple[str, float]] = {
    "b1": ("rat.a0", 1.0),
    "b2": ("rat.a1", 1.0),
    "b3": ("rat.a2", 1.0),
    "b4": ("rat.a3", 1.0),
    "b5": ("rat.b1", 1.0),
    "b6": ("rat.b2", 1.0),
    "b7": ("rat.b3", 1.0),
}
_LOGISTIC: dict[str, tuple[str, float]] = {
    "b1": ("log.amplitude", 1.0),
    "b2": ("log.shift", 1.0),
    "b3": ("log.rate", 1.0),
}
_RICHARDS: dict[str, tuple[str, float]] = {**_LOGISTIC, "b4": ("log.shape", 1.0)}
_CHWIRUT: dict[str, tuple[str, float]] = {
    "b1": ("eol.rate", 1.0),
    "b2": ("eol.lin_const", 1.0),
    "b3": ("eol.lin_slope", 1.0),
}

STDERR_COEFFS: dict[str, dict[str, tuple[str, float]]] = {
    "Gauss1": _TWO_GAUSSIAN,
    "Gauss2": _TWO_GAUSSIAN,
    "Gauss3": _TWO_GAUSSIAN,
    "Lanczos1": _LANCZOS,
    "Lanczos2": _LANCZOS,
    "Lanczos3": _LANCZOS,
    "BoxBOD": _BOXBOD,
    "Misra1a": _MISRA1A,
    "Misra1b": _MISRA1B,
    "MGH17": _MGH17,
    "MGH09": _MGH09,
    "Bennett5": _BENNETT5,
    "Eckerle4": _ECKERLE4,
    "Roszman1": _ROSZMAN1,
    "DanWood": _DANWOOD,
    "Kirby2": _RATIONAL_QUADRATIC,
    "Hahn1": _RATIONAL_CUBIC,
    "Thurber": _RATIONAL_CUBIC,
    "Rat42": _LOGISTIC,
    "Rat43": _RICHARDS,
    "Chwirut1": _CHWIRUT,
    "Chwirut2": _CHWIRUT,
}
"""Info:
    NIST parameter -> (fitted parameter key, linear coefficient), per dataset.
    A NIST parameter absent from a dataset's map is one the projection reaches
    nonlinearly; see :data:`STDERR_BLOCKED`.
"""

STDERR_BLOCKED: dict[str, dict[str, str]] = {
    "Eckerle4": {
        "b1": (
            "NIST b1 = amplitude * sigma, a product of two fitted parameters; a "
            "single fitted standard error does not propagate through it."
        ),
    },
    "DanWood": {
        "b2": (
            "NIST b2 = -1/shape, a reciprocal of a fitted parameter; a fitted "
            "standard error does not propagate through it by a constant factor."
        ),
    },
}
"""Info:
    NIST parameters whose certified standard deviation has no comparable fitted
    standard error, with the reason. Both cases are nonlinear reparameterizations.
"""

NULL_CODE_NONLINEAR = "nonlinear_projection"
NULL_CODE_NO_STDERR = "no_fitted_stderr"
NULL_CODE_SOLVER_ERROR = "solver_error"


class DifficultyTierError(ValueError):
    """A NIST fixture docstring does not state the dataset's difficulty tier."""

    def __init__(self, name: str) -> None:
        """Name the fixture whose docstring is missing the tier."""
        super().__init__(
            f"the {name} fixture docstring does not state a NIST difficulty tier",
        )


class ProjectionDriftError(ValueError):
    """The standard-error map disagrees with the audit's own NIST projection."""

    def __init__(self, dataset: str, param: str, mapped: float, projected: float) -> None:
        """Name the parameter whose mapped value contradicts the audit projection."""
        super().__init__(
            f"{dataset}.{param}: the standard-error map yields {mapped}, the audit "
            f"projection yields {projected}; the map has drifted from oracles.audit.nist",
        )


def difficulty(name: str) -> str:
    """Read NIST's difficulty tier for ``name`` out of its fixture module docstring."""
    module = import_module(f"oracles.nist_strd.{name.lower()}")
    doc = module.__doc__ or ""
    for line in doc.splitlines():
        if line.startswith(_CLASSIFIES) and _DIFFICULTY_MARK in line:
            return line.split('**"')[1].split('"**')[0]
    raise DifficultyTierError(name)


def start_values(recipe: Any, start: str) -> dict[str, float]:
    """NIST's certified starting point ``start`` of a recipe's dataset.

    ``START2`` is the recipe's own start (the one the shipped audit fits from);
    ``START1`` is read from the dataset's fixture module.

    Raises:
        ValueError: ``start`` is neither ``START1`` nor ``START2``.
    """
    match start:
        case "START2":
            return recipe.start
        case "START1":
            return dict(import_module(f"oracles.nist_strd.{recipe.name.lower()}").START1)
        case _:
            msg = f"unknown NIST start {start!r} (expected START1 or START2)"
            raise ValueError(msg)


def _spectrafit_fit(
    recipe: Any,
    start: dict[str, float],
) -> tuple[Any, dict[str, float], dict[str, float | None]]:
    """The spectrafit-core fit from ``start``: (result, projected values, stderrs)."""
    res = fit(
        recipe.build(start),
        MeasurementData(x=recipe.x, y=recipe.y),
        FitOptions(solver="lm", max_iterations=MAX_IT, tolerance=TOL),
    )
    values, stderrs = _project_spectrafit(recipe, res)
    return res, values, stderrs


def fit_spectrafit(
    recipe: Any,
    start: dict[str, float] | None = None,
) -> tuple[dict[str, float], dict[str, float | None]]:
    """Fit one recipe with spectrafit-core; return NIST-projected values and stderrs.

    The values come from the audit's own ``project`` callable. The standard errors
    are pulled through :data:`STDERR_COEFFS`, and the projected value is re-derived
    from the same map as a guard: if the map ever drifts from the audit's
    projection, this raises instead of quietly reporting the wrong error.
    ``start`` defaults to the recipe's own start (Start 2).
    """
    _res, values, stderrs = _spectrafit_fit(recipe, recipe.start if start is None else start)
    return values, stderrs


def _project_spectrafit(
    recipe: Any,
    res: Any,
) -> tuple[dict[str, float], dict[str, float | None]]:
    """NIST-projected values and stderrs of a spectrafit-core result (see ``fit_spectrafit``)."""
    values = recipe.project(res)
    stderrs: dict[str, float | None] = {}
    for nist_name in recipe.certified:
        entry = STDERR_COEFFS[recipe.name].get(nist_name)
        if entry is None:
            stderrs[nist_name] = None
            continue
        key, coeff = entry
        fitted = res.params[key]
        if not np.isclose(coeff * fitted.value, values[nist_name], rtol=1e-9, atol=0.0):
            raise ProjectionDriftError(
                recipe.name,
                nist_name,
                coeff * fitted.value,
                values[nist_name],
            )
        stderrs[nist_name] = None if fitted.stderr is None else abs(coeff) * fitted.stderr
    return values, stderrs


def _lmfit_fit(recipe: Any, start: dict[str, float]) -> Any:
    """``lmfit.minimize(method="leastsq")`` from ``start`` at :data:`TOL` (the raw result)."""
    x = np.asarray(recipe.x, dtype=float)
    y = np.asarray(recipe.y, dtype=float)
    names = list(recipe.certified)
    model = MODELS[recipe.name]
    pars = lmfit.Parameters()
    for n in names:
        pars.add(n, value=float(start[n]))
    return lmfit.minimize(
        lambda q, x=x, y=y, model=model, names=names: model(x, *[q[n].value for n in names]) - y,
        pars,
        method="leastsq",
        ftol=TOL,
        xtol=TOL,
        gtol=TOL,
    )


def fit_lmfit(recipe: Any, start: dict[str, float] | None = None) -> dict[str, float]:
    """Fit one recipe with ``lmfit.minimize(method="leastsq")`` at :data:`TOL`."""
    out = _lmfit_fit(recipe, recipe.start if start is None else start)
    return {n: float(out.params[n].value) for n in recipe.certified}


def _scipy_fit(recipe: Any, method: str, start: dict[str, float]) -> Any:
    """``scipy.optimize.least_squares`` from ``start`` at :data:`TOL` (the raw result)."""
    x = np.asarray(recipe.x, dtype=float)
    y = np.asarray(recipe.y, dtype=float)
    names = list(recipe.certified)
    model = MODELS[recipe.name]
    return least_squares(
        lambda p: model(x, *p) - y,
        np.array([float(start[n]) for n in names]),
        method=method,
        ftol=TOL,
        xtol=TOL,
        gtol=TOL,
        max_nfev=MAX_IT,
    )


def fit_scipy(recipe: Any, method: str, start: dict[str, float] | None = None) -> dict[str, float]:
    """Fit one recipe with ``scipy.optimize.least_squares`` at :data:`TOL`."""
    out = _scipy_fit(recipe, method, recipe.start if start is None else start)
    return dict(zip(list(recipe.certified), (float(v) for v in out.x), strict=True))


def worst_lre(values: dict[str, float], recipe: Any) -> float:
    """LRE of the least accurately recovered parameter, against certified values."""
    return min(lre(values[n], recipe.certified[n][0]) for n in recipe.certified)


def sigma_lre(
    stderrs: dict[str, float | None],
    recipe: Any,
) -> tuple[float | None, dict[str, float | None], dict[str, Any] | None]:
    """LRE of the least accurate fitted standard error, or ``None`` with a reason."""
    per_param: dict[str, float | None] = {}
    blocked = STDERR_BLOCKED.get(recipe.name, {})
    missing: list[str] = []
    for name, (_certified, certified_sd) in recipe.certified.items():
        got = stderrs[name]
        if got is None:
            per_param[name] = None
            missing.append(name)
            continue
        per_param[name] = lre(got, certified_sd)
    if not missing:
        return min(v for v in per_param.values() if v is not None), per_param, None
    nonlinear = [n for n in missing if n in blocked]
    code = NULL_CODE_NONLINEAR if nonlinear == missing else NULL_CODE_NO_STDERR
    detail = (
        " ".join(blocked[n] for n in nonlinear)
        if nonlinear == missing
        else f"no fitted standard error for {', '.join(missing)}"
    )
    return None, per_param, {"code": code, "params": missing, "detail": detail}


def solver_column(
    recipe: Any,
    label: str,
    runner: Any,
) -> tuple[float | None, dict[str, Any] | None]:
    """Run one reference solver and reduce it to an LRE, or ``None`` with a reason."""
    try:
        values = runner(recipe)
    except (ValueError, RuntimeError, FloatingPointError, TypeError) as exc:
        return None, {"code": NULL_CODE_SOLVER_ERROR, "detail": f"{label}: {exc}"}
    return worst_lre(values, recipe), None


def build_row(recipe: Any, start: dict[str, float] | None = None) -> dict[str, Any]:
    """Measure all five columns for one NIST dataset (from Start 2 unless ``start``)."""
    values, stderrs = fit_spectrafit(recipe, start)
    sigma, sigma_per_param, sigma_null = sigma_lre(stderrs, recipe)
    columns: dict[str, float | None] = {
        "spectrafit_core": worst_lre(values, recipe),
        "sigma": sigma,
    }
    null_reasons: dict[str, Any] = {}
    if sigma_null is not None:
        null_reasons["sigma"] = sigma_null
    for label, runner in (
        ("lmfit", lambda r: fit_lmfit(r, start)),
        ("scipy_lm", lambda r: fit_scipy(r, "lm", start)),
        ("scipy_trf", lambda r: fit_scipy(r, "trf", start)),
    ):
        value, reason = solver_column(recipe, label, runner)
        columns[label] = value
        if reason is not None:
            null_reasons[label] = reason
    return {
        "name": recipe.name,
        "difficulty": difficulty(recipe.name),
        "n_params": len(recipe.certified),
        "n_obs": len(recipe.x),
        "model": recipe.model,
        "columns": columns,
        "null_reasons": null_reasons,
        "per_param": {n: lre(values[n], recipe.certified[n][0]) for n in recipe.certified},
        "sigma_per_param": sigma_per_param,
    }


# --- Per-start detail (``--start both``) ---------------------------------------
#
# Both certified starts, every implementation, with the least accurate parameter and
# standard error named, the LRE of the residual sum of squares, the success flag and
# the termination reason. The Start 2 table above is left exactly as it was.


class NistCell(BaseModel):
    """One dataset x start x implementation of the detail output."""

    model_config = ConfigDict(extra="forbid")

    dataset: str
    difficulty: str
    start: StartName
    implementation: str
    success: bool | None
    termination: str | None
    error: str | None
    param_lre: dict[str, float]
    param_lre_min: float | None
    param_lre_min_name: str | None
    stderr_lre: dict[str, float | None]
    stderr_lre_min: float | None
    stderr_lre_min_name: str | None
    stderr_missing_reason: str | None
    rss: float | None
    rss_lre: float | None


class StartSummary(BaseModel):
    """Per start and implementation: worst parameter LRE, and what did not converge."""

    model_config = ConfigDict(extra="forbid")

    start: StartName
    implementation: str
    worst_param_lre: float | None
    dataset: str | None
    parameter: str | None
    not_converged: list[dict[str, str | None]]
    no_result: list[dict[str, str | None]]


def least_accurate(per_param: Mapping[str, float | None]) -> tuple[str, float] | None:
    """The least accurately recovered entry: lowest LRE, ties to the first in NIST order."""
    present = [(v, i, k) for i, (k, v) in enumerate(per_param.items()) if v is not None]
    if not present:
        return None
    value, _index, name = min(present)
    return name, value


def stderr_from_jacobian(
    jac: np.ndarray,
    rss: float,
    names: Sequence[str],
) -> dict[str, float | None]:
    r"""Standard errors $\sqrt{\mathrm{diag}\,(J^T J)^{+} \cdot \mathrm{RSS}/(m-n)}$.

    The covariance ``scipy.optimize.curve_fit`` reports with ``absolute_sigma=False``
    (scipy 1.18, ``_minpack_py.curve_fit``): an SVD pseudo-inverse of the final
    Jacobian that drops singular values below $\epsilon \max(m, n)\, s_1$, scaled by
    the residual variance $\mathrm{RSS}/(m-n)$ -- the variance NIST's certified
    standard deviations use. ``None`` where there are no degrees of freedom or the
    variance is not positive and finite.
    """
    out: dict[str, float | None] = {}
    m, n = jac.shape
    if m <= n:
        for k in names:
            out[k] = None
        return out
    _u, s, vt = np.linalg.svd(jac, full_matrices=False)
    keep = s > np.finfo(float).eps * max(jac.shape) * s[0]
    s, vt = s[keep], vt[keep]
    cov = (vt.T / s**2) @ vt * (rss / (m - n))
    for k, c in zip(names, np.diag(cov), strict=True):
        out[k] = float(np.sqrt(c)) if np.isfinite(c) and c > 0 else None
    return out


def _finite_lre(value: float | None, certified: float) -> float | None:
    """``lre`` for a finite value; ``None`` otherwise (``lre`` maps NaN to 15)."""
    return None if value is None or not math.isfinite(value) else lre(value, certified)


def _rss(recipe: Any, values: dict[str, float]) -> float:
    """Residual sum of squares of NIST's own model at ``values``."""
    x = np.asarray(recipe.x, dtype=float)
    y = np.asarray(recipe.y, dtype=float)
    r = y - MODELS[recipe.name](x, *[values[n] for n in recipe.certified])
    return float(r @ r)


def _fit_detail(
    recipe: Any,
    implementation: str,
    start: dict[str, float],
) -> tuple[dict[str, float], dict[str, float | None], bool, str]:
    """(values, stderrs, success, termination reason) of one implementation from ``start``."""
    names = list(recipe.certified)
    match implementation:
        case "spectrafit_core":
            res, values, stderrs = _spectrafit_fit(recipe, start)
            return values, stderrs, bool(res.success), str(res.message)
        case "lmfit":
            out = _lmfit_fit(recipe, start)
            values = {n: float(out.params[n].value) for n in names}
            stderrs = {
                n: None if out.params[n].stderr is None else float(out.params[n].stderr)
                for n in names
            }
            reason = (
                f"ier={getattr(out, 'ier', None)}: {out.message}"
                f" | lmdif: {getattr(out, 'lmdif_message', None)}"
            )
            return values, stderrs, bool(out.success), reason
        case "scipy_lm" | "scipy_trf":
            out = _scipy_fit(recipe, implementation.removeprefix("scipy_"), start)
            values = dict(zip(names, (float(v) for v in out.x), strict=True))
            stderrs = stderr_from_jacobian(
                np.asarray(out.jac, dtype=float),
                2.0 * float(out.cost),
                names,
            )
            return values, stderrs, bool(out.success), f"status={out.status}: {out.message}"
        case _:
            msg = f"unknown implementation {implementation!r}"
            raise ValueError(msg)


def detail_cell(recipe: Any, implementation: str, start: StartName) -> NistCell:
    """Fit one dataset from one start with one implementation and measure everything.

    A comparator error is recorded in the cell (as ``solver_column`` does for the table);
    a spectrafit-core error, including a projection drift, propagates as in ``build_row``.
    """
    base: dict[str, Any] = {
        "dataset": recipe.name,
        "difficulty": difficulty(recipe.name),
        "start": start,
        "implementation": implementation,
    }
    try:
        values, stderrs, success, termination = _fit_detail(
            recipe,
            implementation,
            start_values(recipe, start),
        )
    except (ValueError, RuntimeError, FloatingPointError, TypeError) as exc:
        if implementation == "spectrafit_core":
            raise
        return NistCell(
            **base,
            success=None,
            termination=None,
            error=f"{type(exc).__name__}: {exc}",
            param_lre={},
            param_lre_min=None,
            param_lre_min_name=None,
            stderr_lre={},
            stderr_lre_min=None,
            stderr_lre_min_name=None,
            stderr_missing_reason=None,
            rss=None,
            rss_lre=None,
        )
    per_param = {n: _finite_lre(values[n], recipe.certified[n][0]) for n in recipe.certified}
    per_stderr = {n: _finite_lre(stderrs[n], recipe.certified[n][1]) for n in recipe.certified}
    worst = least_accurate(per_param)
    worst_se = least_accurate(per_stderr)
    missing = [n for n, v in per_stderr.items() if v is None]
    reason: str | None = None
    if missing:
        _sigma, _per, null = sigma_lre(stderrs, recipe)
        reason = (
            null["detail"]
            if implementation == "spectrafit_core" and null is not None
            else f"no standard error for {', '.join(missing)}"
        )
    rss = _rss(recipe, values)
    certified_rss = float(import_module(f"oracles.nist_strd.{recipe.name.lower()}").RSS)
    return NistCell(
        **base,
        success=success,
        termination=termination,
        error=None,
        param_lre={n: v for n, v in per_param.items() if v is not None},
        param_lre_min=None if worst is None else worst[1],
        param_lre_min_name=None if worst is None else worst[0],
        stderr_lre=per_stderr,
        stderr_lre_min=None if worst_se is None else worst_se[1],
        stderr_lre_min_name=None if worst_se is None else worst_se[0],
        stderr_missing_reason=reason,
        rss=rss if math.isfinite(rss) else None,
        rss_lre=_finite_lre(rss, certified_rss),
    )


def summarise_start(
    start: StartName,
    cells: Sequence[NistCell],
    implementations: Sequence[str],
) -> list[StartSummary]:
    """Per implementation: the worst parameter LRE over all datasets of one start.

    Ties go to the first dataset in table order. Datasets whose fit reported
    ``success=False`` are listed with their termination reason; datasets without a
    result (a comparator error) are listed with the error.
    """
    out: list[StartSummary] = []
    for impl in implementations:
        mine = [c for c in cells if c.implementation == impl and c.start == start]
        scored = [c for c in mine if c.param_lre_min is not None]
        worst = min(scored, key=lambda c: c.param_lre_min or 0.0) if scored else None
        out.append(
            StartSummary(
                start=start,
                implementation=impl,
                worst_param_lre=None if worst is None else worst.param_lre_min,
                dataset=None if worst is None else worst.dataset,
                parameter=None if worst is None else worst.param_lre_min_name,
                not_converged=[
                    {"dataset": c.dataset, "termination": c.termination}
                    for c in mine
                    if c.success is False
                ],
                no_result=[
                    {"dataset": c.dataset, "error": c.error} for c in mine if c.error is not None
                ],
            ),
        )
    return out


def summary_line(s: StartSummary) -> str:
    """One printed line per start and implementation."""
    worst = (
        "no result"
        if s.worst_param_lre is None
        else f"{s.worst_param_lre:.2f} ({s.dataset} {s.parameter})"
    )
    nc = ", ".join(f"{d['dataset']} [{d['termination']}]" for d in s.not_converged) or "none"
    nr = ", ".join(f"{d['dataset']} [{d['error']}]" for d in s.no_result) or "none"
    return (
        f"{START_LABELS[s.start]} {s.implementation}: worst parameter LRE {worst}; "
        f"not converged: {nc}; no result: {nr}"
    )


def _spectrafit_core_build() -> dict[str, Any]:
    """Which build of spectrafit-core ran: version, wheel tag, and how it was installed.

    A PyPI wheel carries no ``direct_url.json``; a wheel file installed by path records its
    hash there; ``maturin develop`` and editable installs record ``dir_info``. The table
    must say which of these produced it, because a local build is not the release.
    """
    dist = importlib.metadata.distribution("spectrafit-core")
    wheel = dist.read_text("WHEEL") or ""
    direct_url = json.loads(dist.read_text("direct_url.json") or "null")
    match direct_url:
        case None:
            source = "index"
        case {"dir_info": {"editable": True}}:
            source = "editable local build"
        case {"dir_info": _}:
            source = "local build"
        case {"archive_info": _, "url": url}:
            source = f"wheel file {Path(url).name}"
        case _:
            source = "unknown"
    return {
        "version": dist.version,
        "wheel_tags": [
            ln.split(":", 1)[1].strip() for ln in wheel.splitlines() if ln.startswith("Tag:")
        ],
        "installed_from": source,
        "archive_hash": (direct_url or {}).get("archive_info", {}).get("hash"),
    }


def _host() -> dict[str, Any]:
    """The machine the table was measured on.

    The last significant figures of an ill-conditioned fit depend on the CPU's vector
    instructions, the C maths library and the LAPACK under SciPy, not only on package
    versions: the same release gives different cells on macOS arm64 and Linux x86-64.
    No timestamp is recorded, so a rerun on the same host writes the same bytes.
    """
    # Imported for its side effect: it loads SciPy's LAPACK, as least_squares does, so
    # the loaded-library list below names the one the fits actually used.
    import scipy.linalg

    def build_deps(mod: Any) -> dict[str, Any]:
        deps = mod.show_config(mode="dicts").get("Build Dependencies", {})
        return {
            k: {f: deps[k].get(f) for f in ("name", "version")}
            for k in ("blas", "lapack")
            if k in deps
        }

    host: dict[str, Any] = {
        "node": platform.node(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "kernel": platform.release(),
        "libc": " ".join(platform.libc_ver()).strip() or None,
        "cpu": platform.processor() or None,
        "blas_lapack": {"numpy": build_deps(np), "scipy": build_deps(scipy)},
    }
    simd = re.compile(r"^(sse4_[12]|avx|avx2|fma|avx512\w*|neon|asimd\w*|sve\w*)$")
    match sys.platform:
        case "linux":
            # platform.libc_ver() stops at "2.35"; the distribution's patch level
            # (e.g. "Ubuntu GLIBC 2.35-0ubuntu3.15") is only in ldd's banner.
            ldd = subprocess.run(["ldd", "--version"], capture_output=True, text=True, check=False)
            host["libc_build"] = (ldd.stdout.splitlines() or [None])[0]
            info = Path("/proc/cpuinfo").read_text().splitlines()
            host["cpu"] = next(
                (ln.split(":", 1)[1].strip() for ln in info if ln.startswith("model name")),
                host["cpu"],
            )
            flags = next(
                (
                    ln.split(":", 1)[1].split()
                    for ln in info
                    if ln.startswith(("flags", "Features"))
                ),
                [],
            )
            host["simd"] = sorted(f for f in flags if simd.match(f))
            libs = {
                ln.split()[-1]
                for ln in Path("/proc/self/maps").read_text().splitlines()
                if len(ln.split()) >= 6
                and re.search(r"(openblas|blas|lapack|mkl|libm\.so)", ln.split()[-1])
            }
            host["blas_lapack"]["loaded"] = sorted(
                lib.split("site-packages/", 1)[-1]
                for lib in libs
                if ".cpython-" not in Path(lib).name
            )
        case "darwin":

            def sysctl(*keys: str) -> str:
                return subprocess.run(
                    ["sysctl", *keys],
                    capture_output=True,
                    text=True,
                    check=False,
                ).stdout

            host["cpu"] = sysctl("-n", "machdep.cpu.brand_string").strip() or host["cpu"]
            features = [
                ln.split(":")[0].removeprefix("hw.optional.")
                for ln in sysctl("hw.optional").splitlines()
                if ln.strip().endswith(": 1")
            ]
            host["simd"] = sorted(
                f
                for f in features
                if re.search(r"(neon|AdvSIMD|SVE|SME|FP16|DotProd|BF16|I8MM)", f)
            )
        case _:
            host["simd"] = None
    return host


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Command line: ``--tolerance``, ``--out``, ``--start``."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tolerance",
        type=float,
        default=TOL,
        help="ftol=xtol=gtol for every backend (default: the shipped audit's 1e-12)",
    )
    ap.add_argument("--out", type=Path, default=None, help="output path")
    ap.add_argument(
        "--start",
        choices=("START1", "START2", "both"),
        default="START2",
        help=(
            "NIST certified starting point: START2 (default) writes the table as before; "
            "START1 writes the same table from Start 1; both writes the per-start detail "
            "(least accurate parameter and standard error named, RSS LRE, success, "
            "termination reason) for every implementation"
        ),
    )
    return ap.parse_args(argv)


def default_out(start: str, tol: float) -> Path:
    """Default output file of a ``--start`` choice at tolerance ``tol``."""
    match start:
        case "START2":
            stem = "nist_table2"
        case "START1":
            stem = "nist_table2_start1"
        case _:
            stem = "nist_table2_both"
    suffix = "" if tol == 1e-12 else f"_tol{tol:g}".replace("-", "")
    return Path(__file__).with_name(f"{stem}{suffix}.json")


def _versions() -> dict[str, Any]:
    return {
        "spectrafit_core": _spectrafit_core_build(),
        "python": platform.python_version(),
        "lmfit": lmfit.__version__,
        "scipy": scipy.__version__,
        "numpy": np.__version__,
    }


def _main_table(start: StartName) -> None:
    """The table from one start (``START2`` is byte for byte the table as it always was)."""
    rows = [build_row(r, start_values(r, start)) for r in _RECIPES]
    order = {"Higher": 0, "Average": 1, "Lower": 2}
    rows.sort(key=lambda r: (order[r["difficulty"]], r["columns"]["spectrafit_core"]))
    payload = {
        "generator": Path(__file__).name,
        "tolerance": {"ftol": TOL, "xtol": TOL, "gtol": TOL},
        "start_point": start,
        "start_point_label": START_LABELS[start],
        "versions": _versions(),
        "host": _host(),
        "columns": ["spectrafit_core", "sigma", "lmfit", "scipy_lm", "scipy_trf"],
        "measure": (
            "log-relative error (significant figures of agreement, capped at 15) of "
            "the least accurately recovered parameter against NIST's certified values; "
            "the sigma column applies the same measure to spectrafit-core's fitted "
            "standard errors against NIST's certified standard deviations"
        ),
        "datasets": rows,
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n")

    head = f"{'Dataset':10s} {'Diff':8s} {'Np':>2s} " + " ".join(
        f"{c:>16s}" for c in payload["columns"]
    )
    print(head)
    print("-" * len(head))
    for row in rows:
        cells = " ".join(
            f"{'--':>16s}" if row["columns"][c] is None else f"{row['columns'][c]:16.2f}"
            for c in payload["columns"]
        )
        print(f"{row['name']:10s} {row['difficulty']:8s} {row['n_params']:>2d} {cells}")
    print(f"\n  wrote {OUT.name} ({len(rows)} datasets, tolerance {TOL:g}, {start})")


def _main_both() -> None:
    """Both starts, every implementation: the detail cells and one summary line per start."""
    cells = [
        detail_cell(r, impl, start)
        for start in STARTS
        for r in _RECIPES
        for impl in IMPLEMENTATIONS
    ]
    summary = [s for start in STARTS for s in summarise_start(start, cells, IMPLEMENTATIONS)]
    payload = {
        "generator": Path(__file__).name,
        "tolerance": {"ftol": TOL, "xtol": TOL, "gtol": TOL},
        "starts": list(STARTS),
        "implementations": list(IMPLEMENTATIONS),
        "versions": _versions(),
        "host": _host(),
        "measure": (
            "log-relative error (significant figures of agreement, capped at 15) against "
            "NIST's certified values: per parameter, per standard error, and of the "
            "residual sum of squares (NIST's model at the fitted parameters); the least "
            "accurate parameter and standard error are named"
        ),
        "cells": [c.model_dump() for c in cells],
        "summary": [s.model_dump() for s in summary],
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    for start in STARTS:
        head = f"{START_LABELS[start]:10s} {'Diff':8s} " + " ".join(
            f"{c:>16s}" for c in IMPLEMENTATIONS
        )
        print(head)
        print("-" * len(head))
        for r in _RECIPES:
            mine = {c.implementation: c for c in cells if c.start == start and c.dataset == r.name}
            row = " ".join(
                f"{'--':>16s}"
                if mine[i].param_lre_min is None
                else f"{mine[i].param_lre_min:7.2f} {mine[i].param_lre_min_name or '':>3s}"
                f"{'' if mine[i].success else ' !':>2s}   "
                for i in IMPLEMENTATIONS
            )
            print(f"{r.name:10s} {difficulty(r.name):8s} {row}")
        print()
        for s in summary:
            if s.start == start:
                print(summary_line(s))
        print()
    print(f"  wrote {OUT.name} ({len(cells)} cells, tolerance {TOL:g}; ! = success false)")


def main(argv: Sequence[str] | None = None) -> None:
    """Measure all 22 datasets from the chosen start(s), write the sidecar, print the table."""
    global TOL, OUT
    args = parse_args(argv)
    TOL = args.tolerance
    OUT = args.out or default_out(args.start, TOL)
    match args.start:
        case "START1" | "START2":
            _main_table(args.start)
        case _:
            _main_both()


if __name__ == "__main__":
    main()
