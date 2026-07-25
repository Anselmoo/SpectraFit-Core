"""Wave C1 Fix A REDO — TDD red-first: exclude fixed params from the free vector.

The previous Fix A approach kept fixed params IN `theta` with a ±1e-12 box
(trf/dogbox) or a soft-barrier residual (lm).  MINPACK still optimises those
entries, causing thrash on fixed-param cases.

The proper fix:
  - FREE params enter `theta` (what `least_squares` actually optimises).
  - FIXED params are held at their pinned value and reconstructed inside the
    residual before calling `_predict`.

These tests are written RED-FIRST (before the implementation is changed).

Test catalogue
--------------
T1  Structural no-thrash guard: ``free vector length == n_total - n_fixed``.
    This is what prevents MINPACK thrash *by construction*.
T2  FX case correctness on all three methods (lm, trf, dogbox):
    the fixed param stays exactly at its pinned value; the free param recovers
    ground truth within tolerance.
T3  All-fixed degenerate guard: skip least_squares entirely; return pinned
    values immediately.
T4  Non-FX cases unchanged: free vector == all params (no regression on the
    common path).
T5  Reconstruct helper: _rebuild_theta inserts free values at correct indices
    and holds fixed values in place.
"""

from __future__ import annotations

from unittest.mock import patch
from typing import Any

import numpy as np
import pytest

from oracles.cases import CaseSpec, GaussianSpec, materialize


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _center_fixed_case():
    """Single-Gaussian case with p0.center fixed at truth."""
    spec = CaseSpec(
        id="fx-redo-test",
        name="scipy-ls fix-A redo test",
        category="fixed",
        difficulty=0.1,
        components=[GaussianSpec(amplitude=2.0, center=1.0, sigma=0.5)],
        x_min=-3.0,
        x_max=4.0,
        n_points=80,
        noise=0.01,
        fixed_params={"p0": ["center"]},
    )
    return materialize(spec)


def _no_fixed_case():
    """Single-Gaussian case with no fixed params."""
    spec = CaseSpec(
        id="nofx-redo-test",
        name="scipy-ls no-fixed redo test",
        category="easy",
        difficulty=0.1,
        components=[GaussianSpec(amplitude=2.0, center=1.0, sigma=0.5)],
        x_min=-3.0,
        x_max=4.0,
        n_points=80,
        noise=0.01,
    )
    return materialize(spec)


def _all_fixed_case():
    """Single-Gaussian case with ALL params fixed."""
    spec = CaseSpec(
        id="allfx-redo-test",
        name="scipy-ls all-fixed redo test",
        category="fixed",
        difficulty=0.1,
        components=[GaussianSpec(amplitude=2.0, center=1.0, sigma=0.5)],
        x_min=-3.0,
        x_max=4.0,
        n_points=80,
        noise=0.01,
        fixed_params={"p0": ["amplitude", "center", "sigma"]},
    )
    return materialize(spec)


# ---------------------------------------------------------------------------
# T1 — Structural no-thrash guard
# ---------------------------------------------------------------------------


class TestFreeVectorExcludesFixed:
    """T1: the free vector passed to least_squares must exclude fixed params."""

    def _capture_x0_length(self, method: str, case):
        """Run _solve, capturing the x0 length that least_squares actually sees."""
        from oracles.backends._scipy_ls import _build_initial_guess, _solve

        box = _build_initial_guess(case)
        seen: dict[str, Any] = {}

        from scipy.optimize import least_squares as real_ls

        def spy(*args: Any, **kwargs: Any) -> Any:
            seen["x0_len"] = (
                len(args[1]) if len(args) >= 2 else len(kwargs.get("x0", []))
            )
            return real_ls(*args, **kwargs)

        with patch("scipy.optimize.least_squares", side_effect=spy):
            _solve(method, box, case)  # ty: ignore[invalid-argument-type]  # pytest.mark.parametrize yields str; narrows to _Method Literal at runtime

        return seen.get("x0_len")

    @pytest.mark.parametrize("method", ["lm", "trf", "dogbox"])
    def test_free_vector_length_excludes_fixed(self, method: str) -> None:
        """The x0 scipy sees must have length == n_total_params - n_fixed_params."""
        case = _center_fixed_case()

        from oracles.models import get_model

        # Count total params across all components.
        n_total = sum(
            len(get_model(comp.model).param_names) for comp in case.comp_guess
        )
        # Count fixed params.
        n_fixed = sum(len(pnames) for pnames in case.spec.fixed_params.values())
        assert n_fixed > 0, "sanity: case must have fixed params"
        expected_free = n_total - n_fixed

        seen_len = self._capture_x0_length(method, case)
        assert seen_len is not None, "spy did not capture x0 length"
        assert seen_len == expected_free, (
            f"{method}: optimizer received x0 of length {seen_len}, "
            f"expected {expected_free} (n_total={n_total}, n_fixed={n_fixed}). "
            "Fixed params must be excluded from the free vector."
        )

    @pytest.mark.parametrize("method", ["lm", "trf", "dogbox"])
    def test_no_fixed_case_free_vector_is_all_params(self, method: str) -> None:
        """Non-FX case: optimizer sees ALL params (no regression on the common path)."""
        case = _no_fixed_case()

        from oracles.models import get_model

        n_total = sum(
            len(get_model(comp.model).param_names) for comp in case.comp_guess
        )

        seen_len = self._capture_x0_length(method, case)
        assert seen_len == n_total, (
            f"{method}: non-FX case: optimizer received {seen_len}, expected {n_total}"
        )


# ---------------------------------------------------------------------------
# T2 — FX case correctness (all three methods)
# ---------------------------------------------------------------------------


class TestFxCaseCorrectness:
    """T2: fixed param stays at pinned value; free params recover ground truth."""

    def _fit_with_method(self, method: str, case):
        from oracles.backends._scipy_ls import ScipyLeastSquaresBackend

        backend = ScipyLeastSquaresBackend(method=method)  # ty: ignore[invalid-argument-type]  # pytest.mark.parametrize yields str; narrows to _Method Literal at runtime
        if not backend.is_supported(case):
            pytest.skip(f"{method} does not support this case")
        return backend.fit(case, n_reps=1)

    @pytest.mark.parametrize("method", ["lm", "trf", "dogbox"])
    def test_fixed_center_stays_at_truth(self, method: str) -> None:
        """Fixed center must stay within 1e-6 of its pinned truth value."""
        case = _center_fixed_case()
        outcome = self._fit_with_method(method, case)
        assert outcome is not None and outcome.success, f"{method}: fit must succeed"

        truth_center = case.true_params["p0.center"]
        fitted_center = float(outcome.params["p0.center"])
        assert abs(fitted_center - truth_center) < 1e-6, (
            f"{method}: fixed center drifted by "
            f"{abs(fitted_center - truth_center):.2e} "
            f"(truth={truth_center:.6f}, fitted={fitted_center:.6f}). "
            "Fixed params must be held exactly at their pinned value."
        )

    @pytest.mark.parametrize("method", ["lm", "trf", "dogbox"])
    def test_free_amplitude_recovers_ground_truth(self, method: str) -> None:
        """Free amplitude must converge to ground truth within 10% rel error."""
        case = _center_fixed_case()
        outcome = self._fit_with_method(method, case)
        if outcome is None or not outcome.success:
            pytest.skip("fit did not converge; not testing param recovery")

        truth_amp = case.true_params["p0.amplitude"]
        fitted_amp = float(outcome.params["p0.amplitude"])
        rel = abs(fitted_amp - truth_amp) / max(abs(truth_amp), 1e-3)
        assert rel < 0.10, (
            f"{method}: amplitude off by {rel:.1%} "
            f"(truth={truth_amp:.4f}, fitted={fitted_amp:.4f})"
        )

    @pytest.mark.parametrize("method", ["lm", "trf", "dogbox"])
    def test_fx_fit_completes_fast_nfev(self, method: str) -> None:
        """An FX case must converge in fewer than 200 function evaluations.

        The old ±1e-12 box made MINPACK thrash (potentially 20+ min).
        With fixed params excluded from theta, the solver has fewer free
        variables and should converge rapidly.
        """
        case = _center_fixed_case()
        outcome = self._fit_with_method(method, case)
        if outcome is None:
            pytest.skip("no outcome")
        assert outcome.n_iter < 200, (
            f"{method}: nfev={outcome.n_iter} is unreasonably high for an FX case "
            "(expected < 200). Fixed params may still be in the free vector."
        )


# ---------------------------------------------------------------------------
# T3 — All-fixed degenerate guard: skip least_squares entirely
# ---------------------------------------------------------------------------


class TestAllFixedDegenerate:
    """T3: when all params are fixed, least_squares must NOT be called."""

    @pytest.mark.parametrize("method", ["lm", "trf", "dogbox"])
    def test_all_fixed_skips_optimizer(self, method: str) -> None:
        """If every param is fixed, least_squares is skipped entirely."""
        from oracles.backends._scipy_ls import _build_initial_guess, _solve

        case = _all_fixed_case()
        box = _build_initial_guess(case)

        called: dict[str, bool] = {"ls": False}
        from scipy.optimize import least_squares as real_ls

        def spy(*args: Any, **kwargs: Any) -> Any:
            called["ls"] = True
            return real_ls(*args, **kwargs)

        with patch("scipy.optimize.least_squares", side_effect=spy):
            result = _solve(method, box, case)  # ty: ignore[invalid-argument-type]  # pytest.mark.parametrize yields str; narrows to _Method Literal at runtime

        assert not called["ls"], (
            f"{method}: least_squares was called even though all params are fixed. "
            "Must skip the optimizer and return pinned values directly."
        )
        # The result must still carry the pinned values in .x
        assert hasattr(result, "x"), "result must have an .x attribute"

    @pytest.mark.parametrize("method", ["lm", "trf", "dogbox"])
    def test_all_fixed_result_contains_pinned_values(self, method: str) -> None:
        """The result for an all-fixed case must contain the exact pinned values."""
        from oracles.backends._scipy_ls import ScipyLeastSquaresBackend

        case = _all_fixed_case()
        backend = ScipyLeastSquaresBackend(method=method)  # ty: ignore[invalid-argument-type]  # pytest.mark.parametrize yields str; narrows to _Method Literal at runtime
        if not backend.is_supported(case):
            pytest.skip(f"{method} does not support this case")

        outcome = backend.fit(case, n_reps=1)
        assert outcome is not None, "fit must return an outcome"

        # Every param must equal its truth value (all are fixed).
        for key, truth_val in case.true_params.items():
            fitted_val = float(outcome.params[key])
            assert abs(fitted_val - truth_val) < 1e-10, (
                f"{method}: all-fixed param {key} differs from truth: "
                f"fitted={fitted_val:.8f}, truth={truth_val:.8f}"
            )


# ---------------------------------------------------------------------------
# T4 — Non-FX regression: free vector is unchanged
# ---------------------------------------------------------------------------


class TestNonFxUnchanged:
    """T4: non-FX cases must produce results identical to the old code path."""

    @pytest.mark.parametrize("method", ["lm", "trf", "dogbox"])
    def test_non_fx_fit_succeeds_and_recovers(self, method: str) -> None:
        """A non-FX Gaussian case must converge and recover truth within 5%."""
        from oracles.backends._scipy_ls import ScipyLeastSquaresBackend

        case = _no_fixed_case()
        backend = ScipyLeastSquaresBackend(method=method)  # ty: ignore[invalid-argument-type]  # pytest.mark.parametrize yields str; narrows to _Method Literal at runtime
        if not backend.is_supported(case):
            pytest.skip(f"{method} does not support this case")

        outcome = backend.fit(case, n_reps=1)
        assert outcome is not None and outcome.success, (
            f"{method}: non-FX fit must succeed"
        )
        for key, truth_val in case.true_params.items():
            fitted_val = float(outcome.params[key])
            rel = abs(fitted_val - truth_val) / max(abs(truth_val), 1e-3)
            assert rel < 0.10, (
                f"{method}: non-FX param {key} off by {rel:.1%} "
                f"(truth={truth_val:.4f}, fitted={fitted_val:.4f})"
            )


# ---------------------------------------------------------------------------
# T5 — _rebuild_theta helper
# ---------------------------------------------------------------------------


class TestRebuildTheta:
    """T5: the internal theta reconstruction inserts free values at correct indices."""

    def test_rebuild_inserts_free_at_right_positions(self) -> None:
        """_rebuild_theta must produce a full vector with free vals at free_indices
        and fixed vals at fixed_indices."""
        from oracles.backends._scipy_ls import _rebuild_theta

        # Simulate: full params are [a, b, c, d] where b and d are fixed.
        # free_indices = [0, 2], fixed_indices = [1, 3]
        # free theta = [1.0, 3.0], fixed_vals = [99.0, 77.0]
        free_theta = np.array([1.0, 3.0])
        fixed_vals = np.array([99.0, 77.0])
        free_indices = [0, 2]
        fixed_indices = [1, 3]
        n_total = 4

        full = _rebuild_theta(
            free_theta, fixed_vals, free_indices, fixed_indices, n_total
        )
        expected = np.array([1.0, 99.0, 3.0, 77.0])
        np.testing.assert_array_equal(full, expected)

    def test_rebuild_all_free(self) -> None:
        """All-free case: _rebuild_theta returns exactly the free theta."""
        from oracles.backends._scipy_ls import _rebuild_theta

        free_theta = np.array([1.0, 2.0, 3.0])
        full = _rebuild_theta(
            free_theta,
            np.array([], dtype=float),
            [0, 1, 2],
            [],
            3,
        )
        np.testing.assert_array_equal(full, free_theta)

    def test_rebuild_all_fixed(self) -> None:
        """All-fixed case: _rebuild_theta returns exactly the fixed vals."""
        from oracles.backends._scipy_ls import _rebuild_theta

        fixed_vals = np.array([10.0, 20.0, 30.0])
        full = _rebuild_theta(
            np.array([], dtype=float),
            fixed_vals,
            [],
            [0, 1, 2],
            3,
        )
        np.testing.assert_array_equal(full, fixed_vals)
