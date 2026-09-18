r"""Generate the manuscript's NIST StRD agreement table (Table 2) for all 22 datasets.

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
  (``oracles.audit.nist``) and the scenario tests fit from.
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

Run:  uv run python manuscript/examples/figures/nist_table2.py
"""

from __future__ import annotations

import argparse
import json
from importlib import import_module
from pathlib import Path
from typing import Any

import lmfit
import numpy as np
import scipy
from nist_head_to_head import MODELS, lre
from oracles.audit.nist import _RECIPES, SQRT2
from scipy.optimize import least_squares
from spectrafit_core import FitOptions, MeasurementData, fit

OUT = Path(__file__).with_name("nist_table2.json")
TOL = 1e-12
"""Stopping tolerance for every backend.

The shipped default is the tolerance the audit itself runs at, not a tighter one
chosen for the paper -- quoting a comparison at a tolerance the software does not
actually run at would describe a configuration nobody ships.

`--tolerance` exists so the paper can say what changes at a tighter one and have
the reader check it. The manuscript states that moving to 1e-15 raises several
comparator cells while spectrafit-core's do not; that claim needs a committed
artifact to rest on, so the 1e-15 run is regenerated and shipped beside this one
rather than quoted from a measurement nobody can repeat.
"""
MAX_IT = 10_000
START = "START2"

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


def fit_spectrafit(recipe: Any) -> tuple[dict[str, float], dict[str, float | None]]:
    """Fit one recipe with spectrafit-core; return NIST-projected values and stderrs.

    The values come from the audit's own ``project`` callable. The standard errors
    are pulled through :data:`STDERR_COEFFS`, and the projected value is re-derived
    from the same map as a guard: if the map ever drifts from the audit's
    projection, this raises instead of quietly reporting the wrong error.
    """
    res = fit(
        recipe.build(recipe.start),
        MeasurementData(x=recipe.x, y=recipe.y),
        FitOptions(solver="lm", max_iterations=MAX_IT, tolerance=TOL),
    )
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


def fit_lmfit(recipe: Any) -> dict[str, float]:
    """Fit one recipe with ``lmfit.minimize(method="leastsq")`` at :data:`TOL`."""
    x = np.asarray(recipe.x, dtype=float)
    y = np.asarray(recipe.y, dtype=float)
    names = list(recipe.certified)
    model = MODELS[recipe.name]
    pars = lmfit.Parameters()
    for n in names:
        pars.add(n, value=float(recipe.start[n]))
    out = lmfit.minimize(
        lambda q, x=x, y=y, model=model, names=names: model(x, *[q[n].value for n in names]) - y,
        pars,
        method="leastsq",
        ftol=TOL,
        xtol=TOL,
        gtol=TOL,
    )
    return {n: float(out.params[n].value) for n in names}


def fit_scipy(recipe: Any, method: str) -> dict[str, float]:
    """Fit one recipe with ``scipy.optimize.least_squares`` at :data:`TOL`."""
    x = np.asarray(recipe.x, dtype=float)
    y = np.asarray(recipe.y, dtype=float)
    names = list(recipe.certified)
    model = MODELS[recipe.name]
    out = least_squares(
        lambda p: model(x, *p) - y,
        np.array([float(recipe.start[n]) for n in names]),
        method=method,
        ftol=TOL,
        xtol=TOL,
        gtol=TOL,
        max_nfev=MAX_IT,
    )
    return dict(zip(names, (float(v) for v in out.x), strict=True))


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


def build_row(recipe: Any) -> dict[str, Any]:
    """Measure all five columns for one NIST dataset."""
    values, stderrs = fit_spectrafit(recipe)
    sigma, sigma_per_param, sigma_null = sigma_lre(stderrs, recipe)
    columns: dict[str, float | None] = {
        "spectrafit_core": worst_lre(values, recipe),
        "sigma": sigma,
    }
    null_reasons: dict[str, Any] = {}
    if sigma_null is not None:
        null_reasons["sigma"] = sigma_null
    for label, runner in (
        ("lmfit", fit_lmfit),
        ("scipy_lm", lambda r: fit_scipy(r, "lm")),
        ("scipy_trf", lambda r: fit_scipy(r, "trf")),
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


def main() -> None:
    """Measure all 22 datasets, write the sidecar, and print the table."""
    global TOL, OUT
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tolerance",
        type=float,
        default=TOL,
        help="ftol=xtol=gtol for every backend (default: the shipped audit's 1e-12)",
    )
    ap.add_argument("--out", type=Path, default=None, help="output path")
    args = ap.parse_args()
    TOL = args.tolerance
    OUT = args.out or (
        OUT if TOL == 1e-12 else OUT.with_name(f"nist_table2_tol{TOL:g}.json".replace("-", ""))
    )
    rows = [build_row(r) for r in _RECIPES]
    order = {"Higher": 0, "Average": 1, "Lower": 2}
    rows.sort(key=lambda r: (order[r["difficulty"]], r["columns"]["spectrafit_core"]))
    payload = {
        "generator": Path(__file__).name,
        "tolerance": {"ftol": TOL, "xtol": TOL, "gtol": TOL},
        "start_point": START,
        "start_point_label": "Start 2",
        "versions": {
            "lmfit": lmfit.__version__,
            "scipy": scipy.__version__,
            "numpy": np.__version__,
        },
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
    print(f"\n  wrote {OUT.name} ({len(rows)} datasets, tolerance {TOL:g}, {START})")


if __name__ == "__main__":
    main()
