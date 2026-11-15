"""``FitOptions(jacobian="finite_difference")`` end to end through the PyO3 boundary (#93).

The Rust tests in ``crates/spectrafit-solver/src/jacobian_mode_tests.rs`` prove
the per-kernel switch (every kernel's Jacobian equals an independent
forward-difference reference to 1e-12 relative in the forced mode, and the
analytic mode is the executor Jacobian bit for bit). These tests prove the
option crosses the Python boundary on both entry points (``fit`` and
``fit_fast``) and reaches the solver:

* the forced mode converges to the analytic optimum to finite-difference
  accuracy, while its post-fit standard errors come from the
  finite-difference Jacobian, so it is not bit-identical to the analytic one;
* the default is unchanged: omitting the field and passing ``"analytic"`` give
  bit-identical results;
* ``solver="varpro"`` rejects the forced mode instead of silently running
  analytic derivatives.
"""

from __future__ import annotations

import numpy as np
import pytest
from spectrafit_core import (
    FitGraph,
    FitOptions,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
    fit_fast,
)

_SOLVERS = ("lm", "lm-legacy", "trf", "geodesic", "dogleg", "newton-cg", "irls", "global")


def _data() -> MeasurementData:
    x = np.linspace(-1.0, 5.0, 80)
    y = 5.0 * np.exp(-0.5 * ((x - 2.0) / 0.5) ** 2) + 0.02 * np.sin(7.0 * x)
    return MeasurementData(x=x.tolist(), y=y.tolist())


def _graph() -> FitGraph:
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=4.0),
                    "center": Parameter(value=1.8),
                    "sigma": Parameter(value=0.6),
                },
            ),
        ],
    )


@pytest.mark.parametrize("solver", _SOLVERS)
def test_forced_fd_converges_to_the_analytic_optimum(solver: str) -> None:
    analytic = fit(_graph(), _data(), FitOptions(solver=solver))
    forced = fit(_graph(), _data(), FitOptions(solver=solver, jacobian="finite_difference"))
    assert analytic.success
    assert forced.success, forced.message
    stderr_differs = False
    for key, p_an in analytic.parameters.items():
        p_fd = forced.parameters[key]
        assert p_fd.value == pytest.approx(p_an.value, rel=1e-5, abs=1e-8), key
        stderr_differs |= p_fd.stderr != p_an.stderr
    assert stderr_differs, f"{solver}: fd-mode stderr must come from the FD Jacobian"


def test_forced_fd_reaches_fit_fast() -> None:
    """``fit_fast`` (the benchmark's timed entry point) honours the option too."""
    analytic, _ = fit_fast(_graph(), _data(), FitOptions(solver="lm"))
    forced, _ = fit_fast(_graph(), _data(), FitOptions(solver="lm", jacobian="finite_difference"))
    assert forced.success
    assert any(
        forced.parameters[k].stderr != analytic.parameters[k].stderr for k in analytic.parameters
    )


def test_default_is_bit_identical_to_explicit_analytic() -> None:
    implicit = fit(_graph(), _data(), FitOptions(solver="lm"))
    explicit = fit(_graph(), _data(), FitOptions(solver="lm", jacobian="analytic"))
    for key, p in implicit.parameters.items():
        assert p.value == explicit.parameters[key].value
        assert p.stderr == explicit.parameters[key].stderr
    assert implicit.chi2 == explicit.chi2


def test_varpro_rejects_forced_fd() -> None:
    with pytest.raises(ValueError, match="finite_difference"):
        fit(_graph(), _data(), FitOptions(solver="varpro", jacobian="finite_difference"))
