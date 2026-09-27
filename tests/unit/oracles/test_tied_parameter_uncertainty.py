"""A tied parameter's uncertainty must reflect the tie, not ignore it.

If ``p1.sigma`` is tied to ``p0.sigma``, the fit has one width parameter, not
two. Three things must therefore hold, and any of them failing is a real
defect in the covariance path:

1. DOF counts the tie -- a tied fit has one MORE degree of freedom than the
   same graph fit free (one fewer free parameter).
2. The tied parameter's reported value equals its target's, exactly.
3. Its reported stderr equals its target's, or is explicitly ``None`` --
   never an independent number computed as if it were free.

There are two equivalent ways to tie a parameter in this codebase: a
graph-level ``ExprEdge`` and a per-parameter ``Parameter.expr``. Both are
first-class, both are documented as evaluated identically at fit time (see
``spectrafit_core.graph.FitGraph``), so both are exercised here.
"""

from __future__ import annotations

from typing import Literal

import numpy as np
import pytest
from spectrafit_core import (
    ExprEdge,
    FitGraph,
    FitResult,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

TieMode = Literal["free", "expr_edge", "param_expr"]

_TIE_MODES: tuple[TieMode, ...] = ("expr_edge", "param_expr")
_TRUTH_SIGMA = 0.7


def _make_data() -> MeasurementData:
    """Two well-separated, noisy Gaussians that truly share one width.

    Separation keeps the fit well conditioned; the shared noise seed makes
    the case deterministic across test runs.
    """
    rng = np.random.default_rng(20260821)
    x = np.linspace(-6.0, 6.0, 180)

    def gaussian(amplitude: float, center: float, sigma: float) -> np.ndarray:
        return amplitude * np.exp(-0.5 * ((x - center) / sigma) ** 2)

    y = gaussian(3.0, -1.8, _TRUTH_SIGMA) + gaussian(2.0, 1.8, _TRUTH_SIGMA)
    y = y + rng.normal(scale=0.02, size=x.size)
    return MeasurementData(x=x.tolist(), y=y.tolist())


def _build_graph(tie: TieMode) -> FitGraph:
    """Build the two-Gaussian graph, ``p1.sigma`` tied per ``tie``.

    Args:
        tie: ``"free"`` leaves both sigmas independent; ``"expr_edge"`` ties
            ``p1.sigma`` to ``p0.sigma`` via a graph-level ``ExprEdge``;
            ``"param_expr"`` ties it via ``Parameter.expr`` on ``p1.sigma``
            directly.

    Returns:
        A ``FitGraph`` with two Gaussian nodes ``p0``/``p1``.

    """
    p1_sigma_expr = "p0.sigma" if tie == "param_expr" else None
    p0 = ModelNodeSpec(
        id="p0",
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(value=2.5),
            "center": Parameter(value=-1.5),
            "sigma": Parameter(value=0.9, min=1e-3),
        },
    )
    p1 = ModelNodeSpec(
        id="p1",
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(value=1.7),
            "center": Parameter(value=1.5),
            "sigma": Parameter(value=0.9, min=1e-3, expr=p1_sigma_expr),
        },
    )
    edges = (
        [ExprEdge(target_node="p1", target_param="sigma", expression="p0.sigma")]
        if tie == "expr_edge"
        else []
    )
    return FitGraph(nodes=[p0, p1], expr_edges=edges)


def _fit_two_peaks_with_tie(tie: TieMode) -> FitResult:
    """Fit the two-Gaussian graph under the given tie mode.

    Args:
        tie: See ``_build_graph``.

    Returns:
        The converged ``FitResult``.

    """
    result = fit(_build_graph(tie), _make_data())
    assert result.success, f"fit did not converge for tie={tie!r}: {result.message}"
    return result


# ---------------------------------------------------------------------------
# Fixtures: fit once per tie mode, shared across the three property tests.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def free_result() -> FitResult:
    """The same two-Gaussian graph with both sigmas fit independently."""
    return _fit_two_peaks_with_tie("free")


@pytest.fixture(scope="module", params=_TIE_MODES)
def tied_result(request: pytest.FixtureRequest) -> tuple[TieMode, FitResult]:
    """The two-Gaussian graph with ``p1.sigma`` tied, one fixture per tie mode."""
    tie_mode: TieMode = request.param
    return tie_mode, _fit_two_peaks_with_tie(tie_mode)


# ---------------------------------------------------------------------------
# Property 1: DOF counts the tie.
# ---------------------------------------------------------------------------


def test_tie_increases_degrees_of_freedom(
    tied_result: tuple[TieMode, FitResult],
    free_result: FitResult,
) -> None:
    """One fewer free parameter means one more degree of freedom."""
    tie_mode, result = tied_result
    assert result.dof == free_result.dof + 1, (
        f"tie={tie_mode!r}: dof={result.dof} should be free.dof+1="
        f"{free_result.dof + 1} (free.dof={free_result.dof})"
    )


# ---------------------------------------------------------------------------
# Property 2: the tied parameter's value equals its target's, exactly.
# ---------------------------------------------------------------------------


def test_tied_parameter_value_equals_target(
    tied_result: tuple[TieMode, FitResult],
) -> None:
    """``p1.sigma`` must equal ``p0.sigma`` exactly -- it is the same value."""
    tie_mode, result = tied_result
    tied = result.parameters["p1.sigma"]
    target = result.parameters["p0.sigma"]
    assert tied.value == target.value, (
        f"tie={tie_mode!r}: p1.sigma={tied.value!r} != p0.sigma={target.value!r}"
    )


# ---------------------------------------------------------------------------
# Property 3: the tied parameter carries no independent uncertainty.
# ---------------------------------------------------------------------------


def test_tied_parameter_shares_its_target_uncertainty(
    tied_result: tuple[TieMode, FitResult],
) -> None:
    """``p1.sigma``'s stderr is ``None`` or equals ``p0.sigma``'s -- never independent."""
    tie_mode, result = tied_result
    tied = result.parameters["p1.sigma"]
    target = result.parameters["p0.sigma"]
    assert tied.stderr is None or tied.stderr == target.stderr, (
        f"tie={tie_mode!r}: p1.sigma.stderr={tied.stderr!r} is an independent "
        f"number, not None and not p0.sigma.stderr={target.stderr!r} -- the "
        "covariance path is ignoring the tie"
    )


# ---------------------------------------------------------------------------
# Sanity guard: the free fit's own tied-looking-but-isn't-tied sigma pair
# should *not* trivially satisfy the same-value check above by accident
# (guards against a degenerate/non-converging synthetic case masking a real
# defect in the tied path).
# ---------------------------------------------------------------------------


def test_free_fit_sigmas_are_independently_estimated(free_result: FitResult) -> None:
    """Precondition check: the untied fit's two sigmas each carry a stderr.

    If this fails, the synthetic case itself is degenerate (e.g. one peak's
    width is unidentifiable) and the tied-vs-free DOF/value/stderr
    comparisons above are not meaningful.
    """
    p0_sigma = free_result.parameters["p0.sigma"]
    p1_sigma = free_result.parameters["p1.sigma"]
    assert p0_sigma.stderr is not None, "p0.sigma has no stderr in the free fit"
    assert p1_sigma.stderr is not None, "p1.sigma has no stderr in the free fit"
