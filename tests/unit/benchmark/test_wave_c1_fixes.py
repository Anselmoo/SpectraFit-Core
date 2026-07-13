"""Wave C1 gap-fixes — TDD red-first unit tests.

Fix A: scipy-ls must apply fixed_params (hold the named params fixed).
Fix B: failed-fit sentinel 0.0 → -1.0 for r2 (clearly-impossible value).
Fix C: GET / on the API must return 200 (human landing) not 404.
"""

from __future__ import annotations

import math

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Fix A — scipy-ls fixed_params
# ---------------------------------------------------------------------------


def _center_fixed_case():
    """A single-Gaussian case with p0.center fixed at its truth value."""
    from oracles.cases import CaseSpec, GaussianSpec, materialize

    spec = CaseSpec(
        id="fx-scipy-test",
        name="scipy-ls fixed_params test",
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


class TestScipyLsFixedParams:
    """Fix A: scipy-ls must not vary the params listed in case.fixed_params."""

    def _fit_with_method(self, method: str):
        from oracles.backends._scipy_ls import ScipyLeastSquaresBackend

        case = _center_fixed_case()
        backend = ScipyLeastSquaresBackend(method=method)  # ty: ignore[invalid-argument-type]  # pytest.mark.parametrize yields str; narrows to _Method Literal at runtime
        if not backend.is_supported(case):
            pytest.skip(f"{method} does not support this case")
        return backend.fit(case, n_reps=1), case

    @pytest.mark.parametrize("method", ["trf", "dogbox"])
    def test_fixed_center_stays_at_truth_trf_dogbox(self, method: str) -> None:
        """scipy-ls (trf/dogbox): fixed center must stay within 1e-4 of truth."""
        outcome, case = self._fit_with_method(method)
        assert outcome is not None and outcome.success, f"{method}: fit must succeed"
        truth_center = case.true_params["p0.center"]
        fitted_center = float(outcome.params["p0.center"])
        assert abs(fitted_center - truth_center) < 1e-4, (
            f"{method}: fixed center drifted "
            f"(truth={truth_center:.6f}, fitted={fitted_center:.6f})"
        )

    @pytest.mark.parametrize("method", ["trf", "dogbox"])
    def test_free_amplitude_recovers_trf_dogbox(self, method: str) -> None:
        """scipy-ls (trf/dogbox): free amplitude must recover within 10%."""
        outcome, case = self._fit_with_method(method)
        if outcome is None or not outcome.success:
            pytest.skip("fit did not converge; not testing param recovery")
        truth_amp = case.true_params["p0.amplitude"]
        fitted_amp = float(outcome.params["p0.amplitude"])
        rel = abs(fitted_amp - truth_amp) / max(abs(truth_amp), 1e-3)
        assert rel < 0.10, (
            f"{method}: amplitude off by {rel:.1%} "
            f"(truth={truth_amp:.4f}, fitted={fitted_amp:.4f})"
        )


# ---------------------------------------------------------------------------
# Fix B — failed-fit sentinel -1.0 instead of 0.0
# ---------------------------------------------------------------------------


class TestFailedFitSentinel:
    """Fix B: non-finite r2 yields r2=-1.0, success=False, no raise."""

    def _run_with_bad_outcome(self, r2: float, reduced_chi2: float):
        from unittest.mock import MagicMock, patch

        from oracles.backends._base import Backend
        from oracles.backends._base import BackendOutcome
        from oracles.engine import run_suite
        from oracles.cases import build_catalog

        catalog = build_catalog()[:1]
        case = catalog[0]
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
        bad_outcome = base.model_copy(update={"r2": r2, "reduced_chi2": reduced_chi2})

        backend = MagicMock(spec=Backend)
        backend.name = "test_backend"
        backend.is_supported = MagicMock(return_value=True)

        with patch("oracles.engine._safe_fit", return_value=bad_outcome):
            result = run_suite(catalog, [backend], n_reps=1)
        return result

    def test_non_finite_r2_yields_sentinel_minus_one(self) -> None:
        """r2=-inf must be stored as -1.0, not 0.0."""
        result = self._run_with_bad_outcome(r2=float("-inf"), reduced_chi2=1.0)
        assert len(result) == 1
        for _sid, m in result[0].m.items():
            assert m.r2 == -1.0, f"Expected sentinel -1.0 for r2, got {m.r2}"

    def test_nan_r2_yields_sentinel_minus_one(self) -> None:
        """r2=NaN must be stored as -1.0, not 0.0."""
        result = self._run_with_bad_outcome(r2=float("nan"), reduced_chi2=1.0)
        for _sid, m in result[0].m.items():
            assert m.r2 == -1.0, f"Expected sentinel -1.0, got {m.r2}"

    def test_sentinel_is_finite(self) -> None:
        """The sentinel -1.0 is finite (no ValidationError)."""
        result = self._run_with_bad_outcome(r2=float("-inf"), reduced_chi2=1.0)
        for _sid, m in result[0].m.items():
            assert math.isfinite(m.r2)

    def test_success_is_false_with_sentinel(self) -> None:
        """success=False whenever the sentinel is applied."""
        result = self._run_with_bad_outcome(r2=float("-inf"), reduced_chi2=1.0)
        for _sid, m in result[0].m.items():
            assert m.success is False


# ---------------------------------------------------------------------------
# Fix C — API root returns 200 (not 404)
# ---------------------------------------------------------------------------


class TestApiRootLanding:
    """Fix C: GET / returns 200, not a bare 404."""

    def _client(self):
        from fastapi.testclient import TestClient

        from oracles.api import app

        return TestClient(app)

    def test_root_returns_200_not_404(self) -> None:
        """GET / must return HTTP 200 (human landing, not a bare 404)."""
        client = self._client()
        resp = client.get("/")
        assert resp.status_code in (200, 307, 301, 302), (
            f"GET / returned {resp.status_code}; expected 200 or redirect"
        )

    def test_root_is_not_bare_detail_not_found(self) -> None:
        """The root response body must not be the bare FastAPI 404 detail."""
        client = self._client()
        resp = client.get("/", follow_redirects=True)
        # The bare 404 body is {"detail": "Not Found"}
        try:
            body = resp.json()
        except Exception:
            return  # HTML or other body — fine
        assert not (body == {"detail": "Not Found"}), (
            "GET / returned the bare 404 detail payload"
        )
