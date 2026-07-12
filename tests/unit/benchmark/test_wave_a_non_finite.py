"""TDD red-first: Finding #1 — non-finite r2/reduced_chi2 must be handled at the producer.

One backend outcome with r2=-inf or reduced_chi2=inf must NOT raise from run_suite
(ValidationError sinking the entire run).  Instead the engine must mark the row as
success=False with safe finite sentinels BEFORE constructing SuiteMetric.

Finding #4: convergence_efficiency stored value and winner_reason _conv_eff helper
must use the same formula (both divide by o.n_iter, not len(ch)-1).
"""

from __future__ import annotations

import math
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from pydantic import ValidationError

from oracles.backends._base import BackendOutcome
from oracles.bench_contract import SuiteMetric


# ---------------------------------------------------------------------------
# Finding #1 helpers
# ---------------------------------------------------------------------------


def _make_real_outcome(case, r2: float, reduced_chi2: float) -> BackendOutcome:
    """A real BackendOutcome instance (not a mock) with controllable r2/reduced_chi2.

    Uses model_copy to override the metric fields on an otherwise valid object.
    The best_fit shape matches the case's y so _red_chi2_weighted doesn't fail.
    """
    y = np.asarray(case.y, dtype=float)
    base = BackendOutcome(
        backend="test",
        success=True,
        r2=0.99,
        chi2=1.0,
        reduced_chi2=1.0,
        aic=10.0,
        bic=12.0,
        n_iter=10,
        params={},
        param_stderr={},
        best_fit=y.copy(),
        cost_history=[],
        gradient_norm_history=[],
        history_source="reconstructed",
        timing_ms=[10.0, 11.0],
    )
    return base.model_copy(update={"r2": r2, "reduced_chi2": reduced_chi2})


class TestNonFiniteOutcomeDoesNotSinkBuildReport:
    """#1: non-finite r2 / reduced_chi2 must not raise ValidationError from run_suite."""

    def _run_with_bad_outcome(self, r2: float, reduced_chi2: float):
        """Helper: run run_suite for 1 case with one backend that returns a bad outcome."""
        from oracles.backends._base import Backend
        from oracles.engine import run_suite
        from oracles.cases import build_catalog

        catalog = build_catalog()[:1]
        case = catalog[0]
        bad_outcome = _make_real_outcome(case, r2=r2, reduced_chi2=reduced_chi2)

        backend = MagicMock(spec=Backend)
        backend.name = "test_backend"
        backend.is_supported = MagicMock(return_value=True)

        with patch("oracles.engine._safe_fit", return_value=bad_outcome):
            result = run_suite(catalog, [backend], n_reps=1)
        return result

    def test_non_finite_r2_does_not_raise_validation_error(self) -> None:
        """run_suite with an outcome whose r2=-inf must not raise ValidationError."""
        result = self._run_with_bad_outcome(r2=float("-inf"), reduced_chi2=1.0)
        assert isinstance(result, list)

    def test_non_finite_reduced_chi2_does_not_raise(self) -> None:
        """run_suite with outcome.reduced_chi2=inf must not raise ValidationError."""
        result = self._run_with_bad_outcome(r2=0.99, reduced_chi2=float("inf"))
        assert isinstance(result, list)

    def test_non_finite_r2_row_is_marked_success_false(self) -> None:
        """When r2 is non-finite the resulting SuiteMetric must have success=False."""
        result = self._run_with_bad_outcome(r2=float("-inf"), reduced_chi2=1.0)
        assert len(result) == 1
        for _sid, m in result[0].m.items():
            assert m.success is False, (
                f"Expected success=False for non-finite r2 row in backend {_sid}"
            )

    def test_non_finite_r2_sentinel_is_finite(self) -> None:
        """The stored r2 value must be finite (not inf/NaN) even when outcome.r2=-inf."""
        result = self._run_with_bad_outcome(r2=float("-inf"), reduced_chi2=1.0)
        for _sid, m in result[0].m.items():
            assert math.isfinite(m.r2), f"r2 must be finite, got {m.r2}"
            assert math.isfinite(m.red_chi2), f"red_chi2 must be finite, got {m.red_chi2}"

    def test_nan_r2_does_not_raise(self) -> None:
        """run_suite with outcome.r2=NaN must not raise ValidationError."""
        result = self._run_with_bad_outcome(r2=float("nan"), reduced_chi2=1.0)
        assert isinstance(result, list)

    def test_non_finite_reduced_chi2_row_is_marked_success_false(self) -> None:
        """When reduced_chi2=inf the resulting SuiteMetric must have success=False."""
        result = self._run_with_bad_outcome(r2=0.99, reduced_chi2=float("inf"))
        assert len(result) == 1
        for _sid, m in result[0].m.items():
            assert m.success is False, (
                f"Expected success=False for non-finite reduced_chi2 in backend {_sid}"
            )

    def test_suite_metric_validator_still_rejects_direct_construction(self) -> None:
        """The SuiteMetric validator is NOT weakened — direct construction with inf still raises."""
        with pytest.raises(ValidationError):
            SuiteMetric(
                speedup=1.0,
                r2=float("-inf"),
                red_chi2=1.0,
                med_ms=10.0,
                param_err=0.0,
                success=True,
            )

    def test_suite_metric_validator_rejects_nan_red_chi2(self) -> None:
        """Direct SuiteMetric construction with NaN red_chi2 still raises."""
        with pytest.raises(ValidationError):
            SuiteMetric(
                speedup=1.0,
                r2=0.99,
                red_chi2=float("nan"),
                med_ms=10.0,
                param_err=0.0,
                success=True,
            )


# ---------------------------------------------------------------------------
# Finding #4: convergence_efficiency consistency
# ---------------------------------------------------------------------------


class TestConvergenceEfficiencyConsistency:
    """#4: winner_reason _conv_eff must use o.n_iter (matching stored convergence_efficiency)."""

    def test_conv_eff_uses_n_iter_not_len_ch_minus_1(self) -> None:
        """_build_winner_reason._conv_eff must compute (ch[0]-ch[-1]) / n_iter,
        matching the stored convergence_efficiency from run_suite."""
        from oracles.engine import _build_winner_reason
        from oracles.cases import build_catalog

        case = build_catalog()[:1][0]
        y = np.asarray(case.y, dtype=float)

        # n_iter=5, cost_history length=3 → len-1=2; the two formulas diverge
        o = BackendOutcome(
            backend="test",
            success=True,
            r2=0.99,
            chi2=90.0,
            reduced_chi2=1.0,
            aic=10.0,
            bic=12.0,
            n_iter=5,
            params={},
            param_stderr={},
            best_fit=y.copy(),
            cost_history=[100.0, 50.0, 10.0],  # len=3, len-1=2
            gradient_norm_history=[],
            history_source="real",
            timing_ms=[10.0, 11.0],
        )

        # stored_ce from run_suite uses o.n_iter=5: (100-10)/5 = 18.0
        stored_ce = (o.cost_history[0] - o.cost_history[-1]) / o.n_iter  # 18.0
        wrong_ce = (o.cost_history[0] - o.cost_history[-1]) / (len(o.cost_history) - 1)  # 45.0

        outcomes: dict = {"a": o, "b": o}
        reason = _build_winner_reason("a", "b", outcomes)

        if reason is not None and "eff=" in reason:
            assert f"{stored_ce:.2e}" in reason, (
                f"winner_reason eff= should be {stored_ce:.2e} (n_iter formula), "
                f"got: {reason!r}. If it shows {wrong_ce:.2e}, the wrong formula is used."
            )
            assert f"{wrong_ce:.2e}" not in reason, (
                f"winner_reason shows {wrong_ce:.2e} (len(ch)-1 formula) instead of "
                f"{stored_ce:.2e} (n_iter formula)"
            )
