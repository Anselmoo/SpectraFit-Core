"""Quantify the standard-error timer asymmetry Validation discloses but never sizes.

`validation.md` states that "SciPy's standard-error computation falls outside
its timer where lmfit's falls inside" and stops there. F-016 asked for the bias
to be moved out of the ratio or reported; the author's own note was that this
is real but need not be over-corrected. This script answers "how much", not by
re-running the reported 151-case/6-backend/5-repetition ladder (expensive, and
the ladder's own headline is not what is in question), but by timing the one
step that differs — the stderr computation itself — in isolation, on a small
stratified sample of the same case catalogue the ladder uses.

lmfit: `composite.fit(y, params, x=x)` computes stderr as part of the single
timed MINPACK call (`_lmfit.py:126`); passing `calc_covar=False` skips it.
The marginal cost is `median(calc_covar=True) - median(calc_covar=False)`
over repeated timed calls on the same case.

SciPy: `_extract_uncertainty` (`_scipy_ls.py:507`, calling `_stderr_from_jac`
at `:472`) runs in `extract()`, after `run()`'s timer has already stopped
(`_base.py:164-167`). It is timed directly here, on the already-solved
`OptimizeResult` `run()` returns, so what is measured is exactly the step the
benchmark's own timer excludes.

Run:  uv run python manuscript/examples/figures/measure_se_timer_bias.py

Writes `se_timer_bias.json` beside itself; prints the summary table.
"""

from __future__ import annotations

import json
import statistics as st
import time
from pathlib import Path
from typing import Any

from oracles.backends._lmfit import LmfitBackend
from oracles.backends._scipy_ls import (
    ScipyLeastSquaresBackend,
    _build_initial_guess,
    _extract_uncertainty,
)
from oracles.cases import BenchCase, build_catalog

OUT = Path(__file__).with_name("se_timer_bias.json")
REPS = 7  # per case, per arm — enough for a stable median without re-running the ladder


def _sample(catalog: list[BenchCase], n: int) -> list[BenchCase]:
    """Cases stratified by point count, excluding tied-parameter cases.

    Tied cases (`expr_edges`) are excluded because `ScipyLeastSquaresBackend`
    cannot fit them at all (`is_supported`) — the sample must be solvable by
    both backends under comparison, or the two arms would not be measuring
    the same cases.
    """
    solvable = [c for c in catalog if not c.spec.expr_edges]
    solvable.sort(key=lambda c: len(c.y))
    step = max(1, len(solvable) // n)
    return solvable[::step][:n]


def _median_ms(fn) -> float:
    times = []
    for _ in range(REPS):
        t0 = time.perf_counter()
        fn()
        times.append((time.perf_counter() - t0) * 1000.0)
    return st.median(times)


def _lmfit_marginal(backend: LmfitBackend, case: BenchCase) -> dict[str, float]:
    """Marginal ms `calc_covar=True` (current, timed) costs over `False`."""
    composite, params, x, y = backend.build(case)
    with_covar = _median_ms(lambda: composite.fit(y, params, x=x, calc_covar=True))
    without_covar = _median_ms(lambda: composite.fit(y, params, x=x, calc_covar=False))
    return {
        "with_covar_ms": round(with_covar, 4),
        "without_covar_ms": round(without_covar, 4),
        "marginal_ms": round(with_covar - without_covar, 4),
    }


def _scipy_marginal(backend: ScipyLeastSquaresBackend, case: BenchCase) -> dict[str, float]:
    """Ms `_extract_uncertainty` costs, run post-hoc on an already-solved fit."""
    model = backend.build(case)
    raw = backend.run(model, case)
    box = _build_initial_guess(case)
    stderr_ms = _median_ms(lambda: _extract_uncertainty(raw, box))
    solve_ms = _median_ms(lambda: backend.run(model, case))
    return {
        "solve_ms": round(solve_ms, 4),
        "stderr_ms": round(stderr_ms, 4),
    }


def main() -> None:
    """Measure the SE marginal cost per backend and write the JSON sidecar."""
    catalog = build_catalog()
    sample = _sample(catalog, 10)

    lmfit_backend = LmfitBackend()
    scipy_backend = ScipyLeastSquaresBackend("lm")

    rows: list[dict[str, Any]] = []
    for case in sample:
        lmfit_row = _lmfit_marginal(lmfit_backend, case)
        scipy_row = _scipy_marginal(scipy_backend, case)
        rows.append(
            {
                "case_id": case.id,
                "n_points": len(case.y),
                "n_components": len(case.comp_true),
                "lmfit": lmfit_row,
                "scipy_ls_lm": scipy_row,
            },
        )

    lmfit_marginal_pct = [
        100.0 * r["lmfit"]["marginal_ms"] / r["lmfit"]["with_covar_ms"]
        for r in rows
        if r["lmfit"]["with_covar_ms"] > 0
    ]
    scipy_excluded_pct = [
        100.0 * r["scipy_ls_lm"]["stderr_ms"] / r["scipy_ls_lm"]["solve_ms"]
        for r in rows
        if r["scipy_ls_lm"]["solve_ms"] > 0
    ]

    summary = {
        "n_cases": len(rows),
        "reps_per_arm": REPS,
        "lmfit_covar_share_of_timed_solve_pct": {
            "median": round(st.median(lmfit_marginal_pct), 2),
            "min": round(min(lmfit_marginal_pct), 2),
            "max": round(max(lmfit_marginal_pct), 2),
        },
        "scipy_stderr_share_of_untimed_step_pct": {
            "median": round(st.median(scipy_excluded_pct), 2),
            "min": round(min(scipy_excluded_pct), 2),
            "max": round(max(scipy_excluded_pct), 2),
        },
    }

    header = f"{'case':10s} {'n':>5s} {'lmfit ms':>10s} {'w/o covar':>10s} {'marg %':>8s}   {'scipy solve':>12s} {'stderr ms':>10s} {'excl %':>8s}"
    print(header)
    print("-" * len(header))
    for r in rows:
        lm = r["lmfit"]
        sp = r["scipy_ls_lm"]
        marg_pct = (
            100.0 * lm["marginal_ms"] / lm["with_covar_ms"] if lm["with_covar_ms"] > 0 else 0.0
        )
        excl_pct = 100.0 * sp["stderr_ms"] / sp["solve_ms"] if sp["solve_ms"] > 0 else 0.0
        print(
            f"{r['case_id']:10s} {r['n_points']:5d} {lm['with_covar_ms']:10.3f} "
            f"{lm['without_covar_ms']:10.3f} {marg_pct:7.2f}%   "
            f"{sp['solve_ms']:12.3f} {sp['stderr_ms']:10.4f} {excl_pct:7.2f}%",
        )
    print()
    print(
        f"lmfit: covar computation is {summary['lmfit_covar_share_of_timed_solve_pct']['median']}% "
        f"of its timed solve (median), range "
        f"[{summary['lmfit_covar_share_of_timed_solve_pct']['min']}, "
        f"{summary['lmfit_covar_share_of_timed_solve_pct']['max']}]%",
    )
    print(
        f"scipy: stderr computation, excluded from its timer, would add "
        f"{summary['scipy_stderr_share_of_untimed_step_pct']['median']}% "
        f"to the timed solve (median), range "
        f"[{summary['scipy_stderr_share_of_untimed_step_pct']['min']}, "
        f"{summary['scipy_stderr_share_of_untimed_step_pct']['max']}]%",
    )

    OUT.write_text(json.dumps({"cases": rows, "summary": summary}, indent=2) + "\n")
    print(f"\nwrote {OUT.name}")


if __name__ == "__main__":
    main()
