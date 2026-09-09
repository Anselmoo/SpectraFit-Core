"""Fit every implemented NIST StRD dataset with spectrafit-core and with lmfit.

This is the generator behind the NIST agreement figures and the head-to-head
comparison. It fits all datasets registered in ``oracles.audit.nist`` from NIST's
Start 2, with both backends at the same convergence tolerance, and records for
each: the log-relative error of the least accurately recovered parameter, the
iteration and function-evaluation counts, the wall time, and the residual vector.

Two deliberate choices:

* Both backends get the tolerance the shipped audit uses (1e-12), not a tighter
  one chosen here. Quoting a comparison at a tolerance the software does not
  actually run at would describe a configuration nobody ships.
* The residuals are recorded at the FITTED parameters, not the certified ones, so
  the figure shows what each backend's own answer leaves behind.

Run:  uv run python manuscript/examples/figures/nist_head_to_head.py
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import lmfit
import numpy as np
from oracles.audit.nist import _RECIPES
from spectrafit_core import FitOptions, MeasurementData, fit

OUT = Path(__file__).with_name("nist_head_to_head.json")
TOL = 1e-12
MAX_IT = 10_000


def _gauss_exp(x, b1, b2, b3, b4, b5, b6, b7, b8):
    return (
        b1 * np.exp(-b2 * x)
        + b3 * np.exp(-((x - b4) ** 2) / b5**2)
        + b6 * np.exp(-((x - b7) ** 2) / b8**2)
    )


def _lanczos(x, b1, b2, b3, b4, b5, b6):
    return b1 * np.exp(-b2 * x) + b3 * np.exp(-b4 * x) + b5 * np.exp(-b6 * x)


def _rational(x, *b):
    """(b1..bk)/(1+...) — quadratic/quadratic for 5 params, cubic/cubic for 7."""
    if len(b) == 5:
        return (b[0] + b[1] * x + b[2] * x**2) / (1 + b[3] * x + b[4] * x**2)
    return (b[0] + b[1] * x + b[2] * x**2 + b[3] * x**3) / (
        1 + b[4] * x + b[5] * x**2 + b[6] * x**3
    )


# NIST's own model forms, transcribed from the dataset pages the fixtures cite.
MODELS: dict[str, Any] = {
    "Gauss1": _gauss_exp,
    "Gauss2": _gauss_exp,
    "Gauss3": _gauss_exp,
    "Lanczos1": _lanczos,
    "Lanczos2": _lanczos,
    "Lanczos3": _lanczos,
    "BoxBOD": lambda x, b1, b2: b1 * (1.0 - np.exp(-b2 * x)),
    "Misra1a": lambda x, b1, b2: b1 * (1.0 - np.exp(-b2 * x)),
    "Misra1b": lambda x, b1, b2: b1 * (1.0 - (1.0 + b2 * x / 2.0) ** (-2)),
    "MGH17": lambda x, b1, b2, b3, b4, b5: b1 + b2 * np.exp(-b4 * x) + b3 * np.exp(-b5 * x),
    "Bennett5": lambda x, b1, b2, b3: b1 * (b2 + x) ** (-1.0 / b3),
    "MGH09": lambda x, b1, b2, b3, b4: b1 * (x**2 + b2 * x) / (x**2 + b3 * x + b4),
    "Eckerle4": lambda x, b1, b2, b3: (b1 / b2) * np.exp(-0.5 * ((x - b3) / b2) ** 2),
    "Roszman1": lambda x, b1, b2, b3, b4: b1 - b2 * x - np.arctan(b3 / (x - b4)) / np.pi,
    "DanWood": lambda x, b1, b2: b1 * x**b2,
    "Kirby2": _rational,
    "Hahn1": _rational,
    "Thurber": _rational,
    "Rat42": lambda x, b1, b2, b3: b1 / (1.0 + np.exp(b2 - b3 * x)),
    "Rat43": lambda x, b1, b2, b3, b4: b1 / (1.0 + np.exp(b2 - b3 * x)) ** (1.0 / b4),
    "Chwirut1": lambda x, b1, b2, b3: np.exp(-b1 * x) / (b2 + b3 * x),
    "Chwirut2": lambda x, b1, b2, b3: np.exp(-b1 * x) / (b2 + b3 * x),
}


def lre(fitted: float, certified: float) -> float:
    """Significant figures of agreement, capped at double precision."""
    denom = abs(certified)
    rel = abs(fitted - certified) if denom == 0.0 else abs(fitted - certified) / denom
    return 15.0 if rel <= 0.0 else min(15.0, -math.log10(rel))


def main() -> None:
    """Fit every registered dataset with both backends and write the sidecar."""
    rows = []
    for r in _RECIPES:
        x = np.asarray(r.x, dtype=float)
        y = np.asarray(r.y, dtype=float)
        names = list(r.certified)

        t0 = time.perf_counter()
        res = fit(
            r.build(r.start),
            MeasurementData(x=r.x, y=r.y),
            FitOptions(solver="lm", max_iterations=MAX_IT, tolerance=TOL),
        )
        sf_ms = (time.perf_counter() - t0) * 1e3
        got = r.project(res)
        sf = {
            "lre": min(lre(got[n], r.certified[n][0]) for n in names),
            "iters": res.n_iter,
            "fev": res.n_func_evals,
            "ms": sf_ms,
            "resid": [float(v) for v in np.asarray(res.residuals)],
        }

        model = MODELS[r.name]
        pars = lmfit.Parameters()
        for n in names:
            pars.add(n, value=float(r.start[n]))
        t0 = time.perf_counter()
        out = lmfit.minimize(
            lambda q, x=x, y=y, model=model, names=names: (
                model(
                    x,
                    *[q[n].value for n in names],
                )
                - y
            ),
            pars,
            method="leastsq",
            ftol=TOL,
            xtol=TOL,
            gtol=TOL,
        )
        lm_ms = (time.perf_counter() - t0) * 1e3
        lm_fit = model(x, *[out.params[n].value for n in names])
        lm = {
            "lre": min(lre(out.params[n].value, r.certified[n][0]) for n in names),
            "iters": None,
            "fev": out.nfev,
            "ms": lm_ms,
            "resid": [float(v) for v in (y - lm_fit)],
        }

        rows.append(
            {
                "name": r.name,
                "model": r.model,
                "n": len(x),
                "n_params": len(names),
                "x": [float(v) for v in x],
                "y": [float(v) for v in y],
                "spectrafit": sf,
                "lmfit": lm,
                "per_param": {n: lre(got[n], r.certified[n][0]) for n in names},
            },
        )
        print(
            f"  {r.name:9s} n={len(x):>3} p={len(names)}  "
            f"SF lre {sf['lre']:5.2f} it {sf['iters']:>4} fev {sf['fev']:>5} "
            f"{sf['ms']:7.2f}ms  |  LM lre {lm['lre']:5.2f} fev {lm['fev']:>5} {lm['ms']:7.2f}ms",
        )

    OUT.write_text(json.dumps(rows, indent=1) + "\n")
    wins = sum(1 for r in rows if r["spectrafit"]["lre"] > r["lmfit"]["lre"])
    print(f"\n  {len(rows)} datasets; spectrafit-core more accurate on {wins}")
    print(
        f"  total time: spectrafit {sum(r['spectrafit']['ms'] for r in rows):.1f} ms, "
        f"lmfit {sum(r['lmfit']['ms'] for r in rows):.1f} ms",
    )
    print(f"  wrote {OUT.name}")


if __name__ == "__main__":
    main()
