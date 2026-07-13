"""Wave C — W2a dof-mismatch fix for FX/TI cases (TDD red-first).

Invariant: for every (case, backend) audit record, the sidecar ``dof`` must match
the dof the backend used to compute its stored ``reduced_chi2``, so W2a's
recompute ``chi2_red_of(y, fit, None, dof)`` ≡ stored within 1e-6.

Root cause (run_032): the audit record used ``n − len(o.params)`` (TOTAL params),
but lmfit/jax/spectrafit compute reduced_chi2 with ``n − n_free`` (FREE params).
For FX (fixed) and TI (tied) cases n_free < n_total → sidecar dof ≠ backend dof
→ recomputed reduced_chi2 diverges → W2a fails.

Fix: each backend adapter sets ``BackendOutcome.fit_dof`` to the dof it actually
used; the engine audit record reads ``o.fit_dof`` instead of re-deriving it.
"""

from __future__ import annotations

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _gaussian_case_fixed_center():
    """Single-Gaussian case with p0.center fixed (FX-001 analogue)."""
    from oracles.cases import CaseSpec, GaussianSpec, materialize

    spec = CaseSpec(
        id="w2a-dof-test-fx",
        name="gaussian center-fixed (W2a dof test)",
        category="fixed",
        difficulty=0.1,
        components=[GaussianSpec(amplitude=2.0, center=0.5, sigma=0.6)],
        x_min=-3.0,
        x_max=3.0,
        n_points=100,
        noise=0.02,
        fixed_params={"p0": ["center"]},
    )
    return materialize(spec)


def _two_peak_tied_sigma_case():
    """Two-Gaussian case with p1.sigma tied to p0.sigma (TI-001 analogue)."""
    from oracles.cases import CaseSpec, GaussianSpec, materialize

    spec = CaseSpec(
        id="w2a-dof-test-ti",
        name="gaussian shared-sigma (W2a dof test)",
        category="tied",
        difficulty=0.1,
        components=[
            GaussianSpec(amplitude=2.0, center=-1.0, sigma=0.5),
            GaussianSpec(amplitude=1.5, center=1.0, sigma=0.5),
        ],
        x_min=-4.0,
        x_max=4.0,
        n_points=120,
        noise=0.02,
        expr_edges=[
            {"target_node": "p1", "target_param": "sigma", "expression": "p0.sigma"}
        ],
    )
    return materialize(spec)


# ---------------------------------------------------------------------------
# Test: BackendOutcome.fit_dof is set by each adapter
# ---------------------------------------------------------------------------


class TestBackendOutcomeFitDof:
    """Each backend adapter must set fit_dof on the returned BackendOutcome.

    fit_dof is the ACTUAL dof used to compute stored reduced_chi2
    (n − n_free for lmfit/jax/spectrafit; n − n_total for scipy-ls).
    """

    def test_lmfit_fit_dof_equals_n_minus_nvarys_on_fx_case(self) -> None:
        """lmfit FX case: fit_dof == n − nvarys (free params only)."""
        from oracles.backends._lmfit import LmfitBackend

        case = _gaussian_case_fixed_center()
        backend = LmfitBackend()
        outcome = backend.fit(case, n_reps=1)
        assert outcome is not None, "lmfit must converge on a simple Gaussian"

        n = len(case.y)
        # One peak, 3 params (amplitude, center, sigma); center is fixed → 2 free.
        n_total = sum(
            len(comp.to_params()) for comp in case.comp_true
        )
        assert outcome.fit_dof is not None, (
            "LmfitBackend.extract() must set fit_dof"
        )
        # center is the only fixed param → n_free = n_total - 1.
        n_free_expected = n_total - 1  # amplitude + sigma vary; center fixed
        assert outcome.fit_dof == max(n - n_free_expected, 1), (
            f"lmfit fit_dof={outcome.fit_dof} should be n-n_free="
            f"{max(n - n_free_expected, 1)} "
            f"(n={n}, n_total={n_total}, n_free={n_free_expected})"
        )
        # Verify consistency: stored_chi2 / fit_dof ≈ reduced_chi2
        recomputed = outcome.chi2 / outcome.fit_dof
        assert abs(recomputed - outcome.reduced_chi2) < 1e-6, (
            f"chi2/fit_dof ({recomputed:.8f}) != stored reduced_chi2 "
            f"({outcome.reduced_chi2:.8f}); fit_dof={outcome.fit_dof}"
        )

    def test_spectrafit_fit_dof_equals_result_dof_on_fx_case(self) -> None:
        """spectrafit FX case: fit_dof == result.dof (n − n_free from Rust)."""
        from oracles.backends._spectrafit import SpectraFitBackend

        case = _gaussian_case_fixed_center()
        backend = SpectraFitBackend()
        if not backend.is_supported(case):
            pytest.skip("spectrafit not available")
        outcome = backend.fit(case, n_reps=1)
        assert outcome is not None, "spectrafit must converge"

        assert outcome.fit_dof is not None, (
            "SpectraFitBackend.extract() must set fit_dof"
        )
        # Consistency: chi2 / fit_dof ≈ stored reduced_chi2
        recomputed = outcome.chi2 / outcome.fit_dof
        assert abs(recomputed - outcome.reduced_chi2) < 1e-6, (
            f"chi2/fit_dof ({recomputed:.8f}) != stored reduced_chi2 "
            f"({outcome.reduced_chi2:.8f})"
        )

    def test_jax_fit_dof_equals_n_minus_n_free_on_base_case(self) -> None:
        """jax: fit_dof == n − n_free (all-free case; jax doesn't support FX)."""
        pytest.importorskip("jax", reason="jax not installed")
        from oracles.backends._jax import JaxBackend
        from oracles.cases import CaseSpec, GaussianSpec, materialize

        spec = CaseSpec(
            id="w2a-dof-test-jax",
            name="gaussian all-free (W2a jax dof test)",
            category="easy",
            difficulty=0.1,
            components=[GaussianSpec(amplitude=2.0, center=0.5, sigma=0.6)],
            x_min=-3.0,
            x_max=3.0,
            n_points=80,
            noise=0.02,
        )
        case = materialize(spec)
        backend = JaxBackend()
        if not backend.is_supported(case):
            pytest.skip("jax not supported for this case")
        outcome = backend.fit(case, n_reps=1)
        assert outcome is not None

        assert outcome.fit_dof is not None, "JaxBackend.extract() must set fit_dof"
        n = len(case.y)
        n_free = sum(len(get_model(c.model).param_names) for c in case.comp_guess)
        expected_dof = max(n - n_free, 1)
        assert outcome.fit_dof == expected_dof, (
            f"jax fit_dof={outcome.fit_dof}, expected {expected_dof}"
        )

    def test_scipy_fit_dof_is_set(self) -> None:
        """scipy-ls: fit_dof is set (uses n_total for consistency)."""
        from oracles.backends._scipy_ls import ScipyLeastSquaresBackend

        case = _gaussian_case_fixed_center()
        backend = ScipyLeastSquaresBackend(method="trf")  # type: ignore[arg-type]
        if not backend.is_supported(case):
            pytest.skip("scipy-ls trf not available")
        outcome = backend.fit(case, n_reps=1)
        assert outcome is not None

        assert outcome.fit_dof is not None, (
            "ScipyLeastSquaresBackend.extract() must set fit_dof"
        )
        # scipy uses total params; verify stored chi2 consistency
        recomputed = outcome.chi2 / outcome.fit_dof
        assert abs(recomputed - outcome.reduced_chi2) < 1e-6, (
            f"chi2/fit_dof ({recomputed:.8f}) != stored reduced_chi2 "
            f"({outcome.reduced_chi2:.8f})"
        )


# ---------------------------------------------------------------------------
# Test: audit sidecar dof matches backend dof → W2a identity holds
# ---------------------------------------------------------------------------


class TestAuditSidecarDof:
    """The audit sidecar must record the backend's actual dof so W2a passes.

    This test builds an audit record the same way _build_profile does and
    checks that chi2_red_of(y, fit, None, rec["dof"]) == stored within 1e-6.
    """

    def _build_audit_record(self, case, outcome):
        """Replicate _build_profile's audit dict for one (case, backend) pair."""
        y = np.asarray(case.y, dtype=float)
        fit = np.asarray(outcome.best_fit, dtype=float)
        # The FIX: use outcome.fit_dof when available.
        dof = (
            outcome.fit_dof
            if outcome.fit_dof is not None
            else max(int(y.size) - len(outcome.params), 1)
        )
        return {
            "y": y,
            "fit": fit,
            "dof": dof,
            "stored_chi2_red": float(outcome.reduced_chi2),
        }

    def _assert_w2a_identity(self, rec: dict) -> None:
        from oracles.metrics import chi2_red_of

        y = np.asarray(rec["y"], float)
        fit = np.asarray(rec["fit"], float)
        recomputed = chi2_red_of(y, fit, None, rec["dof"])
        delta = abs(recomputed - rec["stored_chi2_red"])
        assert delta < 1e-6, (
            f"W2a identity fails: |recomputed({recomputed:.8f}) "
            f"- stored({rec['stored_chi2_red']:.8f})| = {delta:.2e} "
            f"(dof={rec['dof']})"
        )

    def test_lmfit_fx_case_w2a_identity(self) -> None:
        """lmfit on FX case: audit dof from fit_dof → W2a identity holds."""
        from oracles.backends._lmfit import LmfitBackend

        case = _gaussian_case_fixed_center()
        outcome = LmfitBackend().fit(case, n_reps=1)
        assert outcome is not None
        rec = self._build_audit_record(case, outcome)
        self._assert_w2a_identity(rec)

    def test_spectrafit_fx_case_w2a_identity(self) -> None:
        """spectrafit on FX case: audit dof from fit_dof → W2a identity holds."""
        from oracles.backends._spectrafit import SpectraFitBackend

        case = _gaussian_case_fixed_center()
        backend = SpectraFitBackend()
        if not backend.is_supported(case):
            pytest.skip("spectrafit not available")
        outcome = backend.fit(case, n_reps=1)
        assert outcome is not None
        rec = self._build_audit_record(case, outcome)
        self._assert_w2a_identity(rec)

    def test_lmfit_ti_case_w2a_identity(self) -> None:
        """lmfit on TI case: audit dof from fit_dof → W2a identity holds."""
        from oracles.backends._lmfit import LmfitBackend

        case = _two_peak_tied_sigma_case()
        if not LmfitBackend().is_supported(case):
            pytest.skip("lmfit does not support TI case")
        outcome = LmfitBackend().fit(case, n_reps=1)
        assert outcome is not None
        rec = self._build_audit_record(case, outcome)
        self._assert_w2a_identity(rec)

    def test_old_len_o_params_dof_diverges_on_fx_case(self) -> None:
        """Regression guard: the OLD sidecar dof (n − n_total) causes W2a to fail.

        This test documents WHY the fix is needed: the old formula gives a wrong
        dof for FX cases (fixed center reduces n_free < n_total).
        """
        from oracles.backends._lmfit import LmfitBackend
        from oracles.metrics import chi2_red_of

        case = _gaussian_case_fixed_center()
        outcome = LmfitBackend().fit(case, n_reps=1)
        assert outcome is not None

        y = np.asarray(case.y, float)
        fit = np.asarray(outcome.best_fit, float)
        # OLD formula: n − len(o.params) — uses TOTAL param count.
        old_dof = max(int(y.size) - len(outcome.params), 1)
        recomputed_with_old_dof = chi2_red_of(y, fit, None, old_dof)
        delta = abs(recomputed_with_old_dof - outcome.reduced_chi2)
        # If fit_dof is set correctly (n_free < n_total), the old dof differs.
        if outcome.fit_dof is not None and outcome.fit_dof != old_dof:
            assert delta > 1e-6, (
                f"Expected W2a to fail with old dof={old_dof} but delta={delta:.2e}; "
                f"fit_dof={outcome.fit_dof} — test precondition not met"
            )


def get_model(model_key):
    from oracles.models import get_model as _get_model

    return _get_model(model_key)
