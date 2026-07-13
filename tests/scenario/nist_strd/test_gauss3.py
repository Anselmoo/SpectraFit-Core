"""NIST StRD Gauss3 — multi-component FitGraph V&V (Cycle 16.D).

Extends the Eckerle4 single-Gaussian V&V (Cycle 16) to a 3-component
composite fit: one exponential decay + two Gaussians. NIST classifies
Gauss3 as **"Lower"** difficulty — recovery is robust from both
published starting guesses — which makes it a clean smoke test for
multi-component FitGraph composition vs external certified values.

* Eckerle4 (Cycle 16): single-Gaussian, "Higher" difficulty, sensitive
  to start. Stresses the trust-region step machinery.
* Gauss1 (Cycle 16.A): 3-component composite, "Lower" difficulty,
  robust to start. Stresses spectrafit's `FitGraph` composition + the
  multi-node Jacobian assembly + the multi-component covariance block.
* **Gauss3 (this file)**: 3-component composite, "Lower" difficulty,
  same NIST model, different data + guesses + certified values. Provides
  independent confirmation of the multi-node Jacobian + covariance path.

NIST's model:

    y = b1·exp(-b2·x) + b3·exp(-(x-b4)²/b5²) + b6·exp(-(x-b7)²/b8²)

Parameter mapping (NIST → spectrafit):

* Exponential decay: `DoubleExponential(A1=b1, lam1=b2, A2=0, lam2=*)`
  with A2 fixed at 0 and lam2 fixed at any value (doesn't matter — A2=0
  zeros that term out). One real free param per axis is impossible in
  spectrafit's catalog without a dedicated `SingleExponential` model,
  so we exploit the existing `DoubleExponential` + `vary=False`.

* Gaussian peaks: `Gaussian(A, c, σ)` where
      A_spectrafit = b3 (or b6)
      c_spectrafit = b4 (or b7)
      σ_spectrafit = b5 / √2 (or b8 / √2)
  NIST writes `exp(-(x-c)²/b5²)` (no 1/2 factor); spectrafit uses
  `exp(-(x-c)²/(2σ²))`. Mapping: `2σ² ≡ b5²`, so `σ = b5/√2`.

After fit, recovered (A, c, σ) project back to NIST (b3, b4, b5):
  b3_recovered = A
  b4_recovered = c
  b5_recovered = σ · √2

Source: https://www.itl.nist.gov/div898/strd/nls/data/gauss3.shtml
Cycle 12 audit (design doc removed 2026-06-13; see git history) — NIST StRD as
rung-7 V&V benchmark.
"""

from __future__ import annotations

import math

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
)
from oracles.nist_strd.gauss3 import (
    CERTIFIED,
    DOF,
    N_OBS,
    RSS,
    START1,
    START2,
    X,
    Y,
)


SQRT2 = math.sqrt(2.0)


def _build_graph(start: dict[str, float]) -> FitGraph:
    """Build the 3-component FitGraph matching the NIST Gauss3 model.

    Initial values: NIST's published starting guess (start1 or start2),
    projected through the parameterization mapping.
    """
    # Exponential decay term: A2=0 fixed (lam2 fixed too — doesn't matter).
    exp_node = ModelNodeSpec(
        id="exp",
        model_type=ModelType.DOUBLE_EXPONENTIAL,
        parameters={
            "A1": Parameter(value=start["b1"]),
            "lam1": Parameter(value=start["b2"], min=0.0),
            "A2": Parameter(value=0.0, vary=False),
            "lam2": Parameter(value=1.0, vary=False),
        },
    )
    # First Gaussian: NIST b3, b4, b5 → spectrafit A, c, σ = b5/√2.
    g1_node = ModelNodeSpec(
        id="g1",
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(value=start["b3"], min=0.0),
            "center": Parameter(value=start["b4"]),
            "sigma": Parameter(value=start["b5"] / SQRT2, min=1e-3),
        },
    )
    # Second Gaussian: NIST b6, b7, b8 → spectrafit A, c, σ = b8/√2.
    g2_node = ModelNodeSpec(
        id="g2",
        model_type=ModelType.GAUSSIAN,
        parameters={
            "amplitude": Parameter(value=start["b6"], min=0.0),
            "center": Parameter(value=start["b7"]),
            "sigma": Parameter(value=start["b8"] / SQRT2, min=1e-3),
        },
    )
    return FitGraph(nodes=[exp_node, g1_node, g2_node])


def _measurement() -> MeasurementData:
    return MeasurementData(x=X.tolist(), y=Y.tolist())


def _project_to_nist(result) -> dict[str, float]:  # noqa: ANN001
    """Spectrafit (A, c, σ, A1, lam1) → NIST (b1..b8)."""
    return {
        "b1": result.params["exp.A1"].value,
        "b2": result.params["exp.lam1"].value,
        "b3": result.params["g1.amplitude"].value,
        "b4": result.params["g1.center"].value,
        "b5": result.params["g1.sigma"].value * SQRT2,
        "b6": result.params["g2.amplitude"].value,
        "b7": result.params["g2.center"].value,
        "b8": result.params["g2.sigma"].value * SQRT2,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("start_name,start", [("start1", START1), ("start2", START2)])
def test_gauss3_recovers_nist_certified_parameters(
    start_name: str, start: dict[str, float]
) -> None:
    """From either NIST starting guess, spectrafit recovers all 8 certified
    Gauss3 parameters within 1e-3 relative tolerance.

    Asserts the FitGraph composition (one DoubleExponential + two Gaussians)
    reaches NIST's certified global minimum, not just a nearby local minimum.
    A 1e-3 envelope is tight for an 8-parameter LM fit and catches any
    real Jacobian-assembly bug across the multi-node graph.
    """
    opts = FitOptions(solver="lm", max_iterations=10000, tolerance=1e-12)
    result = fit(_build_graph(start), _measurement(), opts)
    assert result.success is True, (
        f"Gauss3 ({start_name}) did not converge: {result.message}"
    )

    recovered = _project_to_nist(result)
    for name, (certified_val, _) in CERTIFIED.items():
        rel = abs(recovered[name] - certified_val) / abs(certified_val)
        assert rel < 1e-3, (
            f"{name} ({start_name}): recovered {recovered[name]:.6e}, "
            f"certified {certified_val:.6e}, rel {rel:.2e}"
        )


def test_gauss3_rss_matches_nist_certified() -> None:
    """The fitted residual sum of squares matches NIST's certified RSS.

    Certified: 1.2444846360e+03 (10 sig figs).
    Required: 1e-4 relative.
    """
    opts = FitOptions(solver="lm", max_iterations=10000, tolerance=1e-12)
    result = fit(_build_graph(START2), _measurement(), opts)
    assert result.success is True

    rss_recovered = float(result.chi2)
    rel = abs(rss_recovered - RSS) / RSS
    assert rel < 1e-4, (
        f"RSS: recovered {rss_recovered:.10e}, certified {RSS:.10e}, rel {rel:.2e}"
    )


def test_gauss3_reduced_chi2_matches_certified() -> None:
    """Reduced χ² matches NIST RSS/DOF within 1e-4 relative.

    Cross-checks the DOF count: spectrafit must count 250 − 8 = 242 (six
    fixed Parameters — `exp.A2`, `exp.lam2` — are correctly excluded from
    the free-parameter count). A DOF miscount would manifest as a few-percent
    relative error here even when chi² itself is exact.
    """
    opts = FitOptions(solver="lm", max_iterations=10000, tolerance=1e-12)
    result = fit(_build_graph(START2), _measurement(), opts)
    assert result.success is True

    certified_red_chi2 = RSS / DOF
    recovered = float(result.reduced_chi2)
    rel = abs(recovered - certified_red_chi2) / certified_red_chi2
    assert rel < 1e-4, (
        f"reduced χ²: recovered {recovered:.10e}, certified {certified_red_chi2:.10e}, "
        f"rel {rel:.2e}"
    )
    assert result.dof == DOF


def test_gauss3_fixture_is_well_formed() -> None:
    """Smoke check on the embedded NIST fixture."""
    assert N_OBS == 250
    assert DOF == 242
    # NIST x is integer-valued 1..250.
    assert X.shape == (250,)
    assert int(X[0]) == 1 and int(X[-1]) == 250
    assert np.all(np.isfinite(Y))
    # Two visible peaks at b4 ≈ 112 and b7 ≈ 148 in the certified values.
    # The data should show local maxima nearby (within ±10 grid points).
    # 75 % envelope is used because the peaks are broad (σ_1 ≈ 23/√2 ≈ 16,
    # σ_2 ≈ 20/√2 ≈ 14 grid points) and the Gauss3 data has non-trivial
    # noise — the y at the *exact* certified center can sit below the local
    # max within the ±10 window.
    for name in ("b4", "b7"):
        cx, _ = CERTIFIED[name]
        i = int(round(cx)) - 1  # x is 1-indexed; arrays 0-indexed
        window = Y[max(0, i - 10) : min(N_OBS, i + 11)]
        local_max = float(np.max(window))
        ratio = Y[i] / local_max
        assert ratio > 0.75, (
            f"no visible peak near certified {name}={cx:.2f}: Y[{i}]={Y[i]:.2f}, "
            f"window max={local_max:.2f}, ratio={ratio:.3f}"
        )
