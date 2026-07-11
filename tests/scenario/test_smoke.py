"""Canonical regression-smoke gate: spectrafit vs lmfit on the deterministic
single-Gaussian scenario.

Loads ``benchmark/scenarios/regression-smoke-gaussian.yaml``, fits it with both
spectrafit (the Rust subject) and lmfit (the oracle), and asserts:
  1. Each solver recovers amplitude/center/sigma within 1 % relative.
  2. The RSS ratio spectrafit/lmfit is within [0.95, 1.05] — a cross-implementation
     sanity check that catches silent divergences without running the full 139-case
     bench.

Target wall time: <500 ms.  No noise, no outliers, deterministic seed=20260609.
"""

from __future__ import annotations

from pathlib import Path

import lmfit
import numpy as np
import pytest
import yaml

from spectrafit_core import (
    FitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2] / "benchmark" / "scenarios" / "regression-smoke-gaussian.yaml"
)


def _load_scenario() -> dict:
    with _SCENARIO_PATH.open() as fh:
        return yaml.safe_load(fh)


def _gaussian_np(x: np.ndarray, amplitude: float, center: float, sigma: float) -> np.ndarray:
    return amplitude * np.exp(-0.5 * ((x - center) / sigma) ** 2)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def test_regression_smoke_gaussian() -> None:
    """Regression-smoke: spectrafit and lmfit recover noiseless Gaussian within 1 %."""
    scenario = _load_scenario()

    # --- extract ground truth and data ---
    meta = scenario["metadata"]
    assert meta.get("role") == "regression-smoke", "scenario role tag missing"
    assert meta["seed"] == 20260609, "seed mismatch — scenario may have been replaced"

    params_spec = scenario["parameters"]
    A_true = float(params_spec["amplitude"]["true_value"])
    c_true = float(params_spec["center"]["true_value"])
    s_true = float(params_spec["sigma"]["true_value"])

    x = np.asarray(scenario["data"]["x"], dtype=float)
    y = np.asarray(scenario["data"]["y"], dtype=float)

    # --- initial guess: perturb true values by ±10 % ---
    A_init, c_init, s_init = A_true * 0.9, c_true * 1.05, s_true * 1.1

    # ------------------------------------------------------------------ #
    # 1. spectrafit fit
    # ------------------------------------------------------------------ #
    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="p0",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=A_init),
                    "center": Parameter(value=c_init),
                    "sigma": Parameter(value=s_init, min=1e-6),
                },
            )
        ]
    )
    data = MeasurementData(x=x.tolist(), y=y.tolist())
    sf_result = fit(graph, data)

    assert sf_result.success, "spectrafit fit failed to converge"

    sf_amp = sf_result.params["p0.amplitude"].value
    sf_cen = sf_result.params["p0.center"].value
    sf_sig = sf_result.params["p0.sigma"].value

    assert sf_amp == pytest.approx(A_true, rel=0.01), f"spectrafit amplitude off: {sf_amp!r}"
    assert sf_cen == pytest.approx(c_true, rel=0.01), f"spectrafit center off: {sf_cen!r}"
    assert sf_sig == pytest.approx(s_true, rel=0.01), f"spectrafit sigma off: {sf_sig!r}"

    sf_best_fit = _gaussian_np(x, sf_amp, sf_cen, sf_sig)
    sf_rss = float(np.sum((y - sf_best_fit) ** 2))

    # ------------------------------------------------------------------ #
    # 2. lmfit fit (oracle)
    # ------------------------------------------------------------------ #
    lm_model = lmfit.Model(_gaussian_np, prefix="p0_")
    lm_params = lm_model.make_params(amplitude=A_init, center=c_init, sigma=s_init)
    lm_params["p0_sigma"].set(min=1e-6)
    lm_fit_result = lm_model.fit(y, lm_params, x=x)

    assert lm_fit_result.success, "lmfit fit failed to converge"

    lm_amp = lm_fit_result.params["p0_amplitude"].value
    lm_cen = lm_fit_result.params["p0_center"].value
    lm_sig = lm_fit_result.params["p0_sigma"].value

    assert lm_amp == pytest.approx(A_true, rel=0.01), f"lmfit amplitude off: {lm_amp!r}"
    assert lm_cen == pytest.approx(c_true, rel=0.01), f"lmfit center off: {lm_cen!r}"
    assert lm_sig == pytest.approx(s_true, rel=0.01), f"lmfit sigma off: {lm_sig!r}"

    lm_best_fit = np.asarray(lm_fit_result.best_fit, dtype=float)
    lm_rss = float(np.sum((y - lm_best_fit) ** 2))

    # ------------------------------------------------------------------ #
    # 3. Cross-implementation smoke: RSS ratio within [0.95, 1.05]
    #    (both solvers reach the same noise-floor on noiseless data)
    # ------------------------------------------------------------------ #
    if lm_rss > 1e-20:
        ratio = sf_rss / lm_rss
        assert 0.95 <= ratio <= 1.05, (
            f"spectrafit/lmfit RSS ratio {ratio:.4f} outside [0.95, 1.05] — "
            f"sf_rss={sf_rss:.2e}, lm_rss={lm_rss:.2e}"
        )
    else:
        # Both effectively zero — noiseless data converged to machine precision.
        assert sf_rss < 1e-12, f"lmfit RSS near zero but spectrafit RSS={sf_rss:.2e}"
