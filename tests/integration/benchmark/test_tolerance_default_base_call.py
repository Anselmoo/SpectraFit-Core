"""Default-mode outcomes equal a literal base-code library call, bit for bit, on any host.

The stored golden (``test_tolerance_default_golden.py``) is bound to the host that
recorded it. This check runs on every host, in one process: for each default-roster
backend and each golden case it compares the outcome of the default-mode adapter with
the outcome of the library call the base code (34cf94d6) made, written here with the
base's literal arguments.

Independence: the code under test is the tolerance-mode argument construction and
option handling of the adapters (``FitOptions`` settings in ``SpectraFitBackend.build``,
the ``match`` in ``LmfitBackend.run``, the ``tol`` keywords in ``_scipy_ls._solve``,
the solver choice in ``JaxBackend.run``). The base side never uses any of it: it does
not call ``run`` or ``_solve``, builds ``FitOptions`` itself and passes the base's
literal keyword arguments to the library. It shares with the adapter side only what
the tolerance modes did not change since the base commit: ``build`` for the model,
data and start values (spectrafit's ``FitOptions`` from ``build`` is discarded),
the scipy residual builders, the jax residual, and ``extract``.
"""

from __future__ import annotations

import functools
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from oracles.backends import get_backends
from oracles.cases import build_catalog

FIXTURES = Path(__file__).parent / "fixtures"


@functools.cache
def _generator() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "gen_golden_base_call",
        FIXTURES / "gen_tolerance_default_golden.py",
    )
    assert spec is not None
    assert spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@functools.cache
def _cases() -> dict[str, Any]:
    wanted = set(_generator().GOLDEN_CASES)
    return {c.id: c for c in build_catalog() if c.id in wanted}


def _spectrafit_base(backend: Any, case: Any) -> Any:
    """``fit_fast(graph, data, FitOptions(solver=..., max_iterations=...))`` as at 34cf94d6."""
    from spectrafit_core import FitOptions, fit_fast

    graph, data, _adapter_options = backend.build(case)
    match case.solver_hint:
        case "global":
            options = FitOptions(solver=case.solver_hint, max_iterations=500)
        case _:
            options = FitOptions(solver=case.solver_hint, max_iterations=2000)
    return fit_fast(graph, data, options)


def _lmfit_base(backend: Any, case: Any) -> Any:
    """``Model.fit(y, params, x=x[, method=..., fit_kws=...])`` as at 34cf94d6."""
    composite, params, x, y = backend.build(case)
    match case.solver_hint:
        case "global":
            return composite.fit(
                y,
                params,
                x=x,
                method="differential_evolution",
                fit_kws={"seed": 0},
            )
        case _:
            return composite.fit(y, params, x=x)


def _scipy_base(method: str, backend: Any, case: Any) -> Any:
    """``least_squares(residual, x0, method=...[, bounds=...])`` as at 34cf94d6."""
    from oracles.backends._scipy_ls import (
        _make_bounded_residual,
        _make_lm_residual,
        _PinnedResult,
    )
    from scipy.optimize import least_squares

    box = backend.build(case).box
    if not box.free_indices:
        return _PinnedResult(x=box.fixed_vals.copy(), n_data=len(case.y))
    match method:
        case "lm":
            return least_squares(_make_lm_residual(case, box), box.free_x0, method="lm")
        case _:
            return least_squares(
                _make_bounded_residual(case, box),
                box.free_x0,
                method=method,
                bounds=(box.free_lo, box.free_hi),
            )


def _jax_base(backend: Any, case: Any) -> Any:
    """``optx.least_squares`` with ``LevenbergMarquardt(rtol=1e-8, atol=1e-8)`` as at 34cf94d6."""
    import optimistix as optx
    from oracles.backends._jax import _residual_for

    y0, x, y, layout = backend.build(case)
    return optx.least_squares(
        _residual_for(layout),
        optx.LevenbergMarquardt(rtol=1e-8, atol=1e-8),
        y0,
        args=(x, y),
        max_steps=200,
        throw=False,
    )


def _base_raw(backend: Any, case: Any) -> Any:
    """The base code's library call for ``backend`` on ``case``."""
    match backend.name:
        case "spectrafit":
            return _spectrafit_base(backend, case)
        case "lmfit":
            return _lmfit_base(backend, case)
        case "scipy-ls-lm":
            return _scipy_base("lm", backend, case)
        case "scipy-ls-trf":
            return _scipy_base("trf", backend, case)
        case "scipy-ls-dogbox":
            return _scipy_base("dogbox", backend, case)
        case "jax":
            return _jax_base(backend, case)
        case other:
            pytest.fail(f"no base call written for backend {other!r}")


def test_every_default_backend_has_a_base_call() -> None:
    names = {b.name for b in get_backends()}
    assert names <= {"spectrafit", "lmfit", "scipy-ls-lm", "scipy-ls-trf", "scipy-ls-dogbox", "jax"}
    assert "spectrafit" in names


@pytest.mark.parametrize("backend", [b.name for b in get_backends()])
def test_default_mode_equals_the_literal_base_call_on_this_host(backend: str) -> None:
    """Every golden case: the default-mode outcome is bit-identical to the base call's."""
    gen = _generator()
    (adapter,) = [b for b in get_backends(tolerance_mode="default") if b.name == backend]
    (base,) = [b for b in get_backends() if b.name == backend]
    compared = 0
    for cid, case in _cases().items():
        if not adapter.is_supported(case):
            continue
        got = gen.outcome_record(adapter.extract(adapter.run(adapter.build(case), case), case))
        want = gen.outcome_record(base.extract(_base_raw(base, case), case))
        assert got == want, f"{backend} {cid}"
        compared += 1
    assert compared > 0
