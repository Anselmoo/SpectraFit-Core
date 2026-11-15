"""``--tolerance-mode common``: one tolerance setting reaches every library call unchanged.

Each adapter's library call is replaced by a recorder, so the test reads the exact
arguments the adapter would pass. A distinctive value (3e-9) proves the plumbing; the
``common`` roster test proves every adapter receives the same setting object. In the
default mode no tolerance argument is added to any call.
"""

from __future__ import annotations

from typing import Any, Literal

import pytest
import typer
from oracles.backends import get_backends
from oracles.backends._tolerance import (
    COMMON_TOLERANCES,
    StopTolerances,
    tolerances_for,
)
from oracles.cases import CaseSpec, GaussianSpec, materialize
from oracles.cli import _resolve_run_backends, _write_tolerance_sidecar
from oracles.exceptions import BackendError

PROBE = StopTolerances(ftol=3e-9, xtol=3e-9, gtol=3e-9)


def _case(solver_hint: str = "lm"):
    return materialize(
        CaseSpec(
            id="TST-TOL-001",
            name="tolerance plumbing",
            category="easy",
            difficulty=0.1,
            components=[GaussianSpec(amplitude=2.0, center=0.1, sigma=0.7)],
            x_min=-4.0,
            x_max=4.0,
            n_points=60,
            noise=0.01,
            solver_hint=solver_hint,
        ),
    )


class _Recorder:
    def __init__(self, result: Any = None) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.result = result

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls.append((args, kwargs))
        return self.result


# ---------------------------------------------------------------- the setting


def test_common_setting_is_1e_8_for_every_test() -> None:
    assert StopTolerances(ftol=1e-8, xtol=1e-8, gtol=1e-8) == COMMON_TOLERANCES
    assert tolerances_for("common") is COMMON_TOLERANCES
    assert tolerances_for("default") is None


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="tolerance mode"):
        tolerances_for("tight")  # ty: ignore[invalid-argument-type]  # the runtime guard is under test


@pytest.mark.parametrize("bad", [0.0, -1e-8])
def test_tolerances_must_be_positive(bad: float) -> None:
    with pytest.raises(ValueError, match="greater than 0"):
        StopTolerances(ftol=bad, xtol=1e-8, gtol=1e-8)


def test_every_backend_receives_the_same_setting_in_common_mode() -> None:
    backends = get_backends(tolerance_mode="common")
    assert backends
    assert all(b.tolerances is COMMON_TOLERANCES for b in backends)


@pytest.mark.parametrize("call", ["explicit", "no_argument"])
def test_no_backend_receives_a_setting_in_default_mode(call: str) -> None:
    backends = get_backends(tolerance_mode="default") if call == "explicit" else get_backends()
    assert all(b.tolerances is None for b in backends)


# ---------------------------------------------------------------- spectrafit


def test_spectrafit_passes_the_tolerance_to_fit_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    import spectrafit_core
    from oracles.backends._spectrafit import SpectraFitBackend

    rec = _Recorder(result=("result", "best_fit"))
    monkeypatch.setattr(spectrafit_core, "fit_fast", rec)
    b = SpectraFitBackend(tolerances=PROBE)
    case = _case()
    b.run(b.build(case), case)
    (_graph, _data, options), _ = rec.calls[0]
    assert options.tolerance == 3e-9
    assert options.max_iterations == 2000
    assert options.solver == "lm"


def test_spectrafit_default_mode_leaves_fitoptions_untouched() -> None:
    from oracles.backends._spectrafit import SpectraFitBackend

    _graph, _data, options = SpectraFitBackend().build(_case())
    assert "tolerance" not in options.model_fields_set
    assert options.model_fields_set == {"solver", "max_iterations"}


def test_spectrafit_rejects_unequal_tests() -> None:
    from oracles.backends._spectrafit import SpectraFitBackend

    with pytest.raises(BackendError, match="one tolerance"):
        SpectraFitBackend(tolerances=StopTolerances(ftol=1e-8, xtol=1e-9, gtol=1e-8))


# ---------------------------------------------------------------- lmfit


@pytest.mark.parametrize(
    ("tolerances", "fit_kws"),
    [(PROBE, {"ftol": 3e-9, "xtol": 3e-9, "gtol": 3e-9}), (None, None)],
)
def test_lmfit_leastsq_receives_fit_kws(
    monkeypatch: pytest.MonkeyPatch,
    tolerances,
    fit_kws,
) -> None:
    lmfit = pytest.importorskip("lmfit")
    from oracles.backends._lmfit import LmfitBackend

    rec = _Recorder()
    monkeypatch.setattr(lmfit.model.Model, "fit", rec)
    b = LmfitBackend(tolerances=tolerances)
    case = _case()
    b.run(b.build(case), case)
    _args, kwargs = rec.calls[0]
    assert kwargs.get("fit_kws") == fit_kws
    assert "method" not in kwargs  # leastsq, lmfit's default


@pytest.mark.parametrize("tolerances", [PROBE, None])
def test_lmfit_differential_evolution_keeps_its_own_stop(
    monkeypatch: pytest.MonkeyPatch,
    tolerances,
) -> None:
    lmfit = pytest.importorskip("lmfit")
    from oracles.backends._lmfit import LmfitBackend

    rec = _Recorder()
    monkeypatch.setattr(lmfit.model.Model, "fit", rec)
    b = LmfitBackend(tolerances=tolerances)
    case = _case("global")
    b.run(b.build(case), case)
    _args, kwargs = rec.calls[0]
    assert kwargs["method"] == "differential_evolution"
    assert kwargs["fit_kws"] == {"seed": 0}


# ---------------------------------------------------------------- scipy least_squares


@pytest.mark.parametrize("method", ["lm", "trf", "dogbox"])
@pytest.mark.parametrize("tolerances", [PROBE, None])
def test_scipy_least_squares_receives_ftol_xtol_gtol(
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    tolerances,
) -> None:
    scipy_optimize = pytest.importorskip("scipy.optimize")
    from oracles.backends._scipy_ls import ScipyLeastSquaresBackend

    rec = _Recorder()
    monkeypatch.setattr(scipy_optimize, "least_squares", rec)
    b = ScipyLeastSquaresBackend(method, tolerances=tolerances)  # ty: ignore[invalid-argument-type]  # parametrize yields str
    case = _case()
    b.run(b.build(case), case)
    _args, kwargs = rec.calls[0]
    assert kwargs["method"] == method
    if tolerances is None:
        assert not {"ftol", "xtol", "gtol"} & set(kwargs)
    else:
        assert (kwargs["ftol"], kwargs["xtol"], kwargs["gtol"]) == (3e-9, 3e-9, 3e-9)


# ---------------------------------------------------------------- jax / optimistix


@pytest.mark.parametrize(("tolerances", "expected"), [(PROBE, 3e-9), (None, 1e-8)])
def test_optimistix_receives_rtol_atol(
    monkeypatch: pytest.MonkeyPatch,
    tolerances,
    expected,
) -> None:
    optx = pytest.importorskip("optimistix")
    from oracles.backends._jax import JaxBackend

    solver_rec = _Recorder(result="solver")
    solve_rec = _Recorder(result="solution")
    monkeypatch.setattr(optx, "LevenbergMarquardt", solver_rec)
    monkeypatch.setattr(optx, "least_squares", solve_rec)
    b = JaxBackend(tolerances=tolerances)
    case = _case()
    b.run(b.build(case), case)
    _args, kwargs = solver_rec.calls[0]
    assert kwargs == {"rtol": expected, "atol": expected}
    _args, solve_kwargs = solve_rec.calls[0]
    assert solve_kwargs["max_steps"] == 200


def test_optimistix_rejects_unequal_step_and_residual_tests() -> None:
    pytest.importorskip("optimistix")
    from oracles.backends._jax import JaxBackend

    with pytest.raises(BackendError, match="rtol"):
        JaxBackend(tolerances=StopTolerances(ftol=1e-8, xtol=1e-7, gtol=1e-8))


# ---------------------------------------------------------------- default mode: the base call, exactly
#
# In the default mode each adapter makes exactly the library call of the base code
# (34cf94d6): the same function, the same positional arguments and the same keyword
# arguments, no tolerance keyword. These pins hold on every host; they are the
# CPU-independent half of "default mode is bit-identical to the base".


@pytest.mark.parametrize(("solver_hint", "max_iterations"), [("lm", 2000), ("global", 500)])
def test_spectrafit_default_mode_calls_fit_fast_with_the_base_options(
    monkeypatch: pytest.MonkeyPatch,
    solver_hint: str,
    max_iterations: int,
) -> None:
    import spectrafit_core
    from oracles.backends._spectrafit import SpectraFitBackend

    rec = _Recorder(result=("result", "best_fit"))
    monkeypatch.setattr(spectrafit_core, "fit_fast", rec)
    b = SpectraFitBackend()
    case = _case(solver_hint)
    graph, data, options = b.build(case)
    b.run((graph, data, options), case)
    (args, kwargs) = rec.calls[0]
    assert len(rec.calls) == 1
    assert kwargs == {}
    assert len(args) == 3
    assert args[0] is graph
    assert args[1] is data
    assert args[2] is options
    assert options.model_fields_set == {"solver", "max_iterations"}
    assert (options.solver, options.max_iterations) == (solver_hint, max_iterations)


def test_lmfit_default_mode_calls_leastsq_exactly_as_the_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lmfit = pytest.importorskip("lmfit")
    from oracles.backends._lmfit import LmfitBackend

    rec = _Recorder()
    monkeypatch.setattr(lmfit.model.Model, "fit", rec)
    b = LmfitBackend()
    case = _case()
    composite, params, x, y = b.build(case)
    b.run((composite, params, x, y), case)
    assert len(rec.calls) == 1
    args, kwargs = rec.calls[0]
    assert len(args) == 2  # Model.fit(y, params, x=x); the recorder is not bound
    assert args[0] is y
    assert args[1] is params
    assert set(kwargs) == {"x"}
    assert kwargs["x"] is x


def test_lmfit_default_mode_calls_differential_evolution_exactly_as_the_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lmfit = pytest.importorskip("lmfit")
    from oracles.backends._lmfit import LmfitBackend

    rec = _Recorder()
    monkeypatch.setattr(lmfit.model.Model, "fit", rec)
    b = LmfitBackend()
    case = _case("global")
    composite, params, x, y = b.build(case)
    b.run((composite, params, x, y), case)
    assert len(rec.calls) == 1
    args, kwargs = rec.calls[0]
    assert len(args) == 2
    assert args[0] is y
    assert args[1] is params
    assert set(kwargs) == {"x", "method", "fit_kws"}
    assert kwargs["x"] is x
    assert kwargs["method"] == "differential_evolution"
    assert kwargs["fit_kws"] == {"seed": 0}


@pytest.mark.parametrize("method", ["lm", "trf", "dogbox"])
def test_scipy_default_mode_calls_least_squares_exactly_as_the_base(
    monkeypatch: pytest.MonkeyPatch,
    method: Literal["lm", "trf", "dogbox"],
) -> None:
    scipy_optimize = pytest.importorskip("scipy.optimize")
    from oracles.backends._scipy_ls import ScipyLeastSquaresBackend

    rec = _Recorder()
    monkeypatch.setattr(scipy_optimize, "least_squares", rec)
    b = ScipyLeastSquaresBackend(method)
    case = _case()
    ctx = b.build(case)
    b.run(ctx, case)
    assert len(rec.calls) == 1
    args, kwargs = rec.calls[0]
    assert len(args) == 2  # least_squares(residual, x0, ...)
    assert callable(args[0])
    assert args[1] is ctx.box.free_x0
    match method:
        case "lm":
            assert kwargs == {"method": "lm"}
        case "trf" | "dogbox":
            assert set(kwargs) == {"method", "bounds"}
            assert kwargs["method"] == method
            lo, hi = kwargs["bounds"]
            assert lo is ctx.box.free_lo
            assert hi is ctx.box.free_hi


def test_optimistix_default_mode_builds_and_calls_the_solver_exactly_as_the_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    optx = pytest.importorskip("optimistix")
    from oracles.backends._jax import JaxBackend

    solver_rec = _Recorder(result="solver")
    solve_rec = _Recorder(result="solution")
    monkeypatch.setattr(optx, "LevenbergMarquardt", solver_rec)
    monkeypatch.setattr(optx, "least_squares", solve_rec)
    b = JaxBackend()
    case = _case()
    y0, x, y, layout = b.build(case)
    b.run((y0, x, y, layout), case)
    assert solver_rec.calls == [((), {"rtol": 1e-8, "atol": 1e-8})]
    assert len(solve_rec.calls) == 1
    args, kwargs = solve_rec.calls[0]
    assert len(args) == 3  # least_squares(residual, solver, y0, ...)
    assert callable(args[0])
    assert args[1] == "solver"
    assert args[2] is y0
    assert set(kwargs) == {"args", "max_steps", "throw"}
    assert kwargs["args"][0] is x
    assert kwargs["args"][1] is y
    assert len(kwargs["args"]) == 2
    assert kwargs["max_steps"] == 200
    assert kwargs["throw"] is False


def test_every_default_backend_has_a_default_call_pin() -> None:
    pinned = {"spectrafit", "lmfit", "scipy-ls-lm", "scipy-ls-trf", "scipy-ls-dogbox", "jax"}
    assert {b.name for b in get_backends()} <= pinned


# ---------------------------------------------------------------- CLI


def test_cli_resolves_common_mode_for_every_backend() -> None:
    resolved, _ = _resolve_run_backends(None, None, "common")
    assert all(b.tolerances is COMMON_TOLERANCES for b in resolved)


def test_cli_default_mode_is_the_default() -> None:
    resolved, _ = _resolve_run_backends(None, None)
    assert all(b.tolerances is None for b in resolved)


def test_cli_rejects_an_unknown_mode() -> None:
    with pytest.raises(typer.BadParameter, match="tolerance mode"):
        _resolve_run_backends(None, None, "tight")


def test_sidecar_only_in_common_mode(tmp_path) -> None:
    _write_tolerance_sidecar(tmp_path, "default")
    assert not (tmp_path / "tolerances.json").exists()
    _write_tolerance_sidecar(tmp_path, "common")
    import json

    rec = json.loads((tmp_path / "tolerances.json").read_text(encoding="utf-8"))
    assert rec == {"mode": "common", "tolerances": {"ftol": 1e-8, "xtol": 1e-8, "gtol": 1e-8}}
