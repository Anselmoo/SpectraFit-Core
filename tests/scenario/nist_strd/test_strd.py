"""NIST StRD external V&V — certified-value benchmark (ground-truth rung 6→7).

The NIST Statistical Reference Datasets (StRD) Nonlinear Regression collection is
the canonical certified benchmark the nonlinear-fitting community uses:
27 problems with parameter values, standard errors, and residual sum of squares
all certified to 10 significant figures by NIST using extended-precision
arithmetic. lmfit ships ``test_NIST.py`` against the same set; scipy uses subsets
in its regression suite. The Cycle 12 upstream audit named this as the single
highest-leverage V&V upgrade for spectrafit-core.

This file pins one problem — **Eckerle4** — which is the cleanest map to
spectrafit-core's model catalog: it's a single Gaussian in a non-standard
parameterization (area-normalized rather than peak-height). NIST classifies it
as **"Higher"** difficulty (one of 8 hardest in the catalog) — the recovery is
sensitive to the starting guess and to floating-point accumulation order, so a
green test here is strong evidence that:

* The Gaussian kernel formula is exactly right (Cycle 3-4 metamorphic tests
  already cover this; Eckerle4 cross-validates against an external oracle).
* The LM convergence reaches the certified minimum (not just a nearby
  local minimum).
* The covariance-from-Jacobian path produces stderrs consistent with NIST's
  certified ones (within published uncertainty + numerical headroom).

Sources:
- NIST StRD Eckerle4: https://www.itl.nist.gov/div898/strd/nls/data/eckerle4.shtml
- Cycle 12 audit (design doc removed 2026-06-13; see git history) — NIST StRD as
  rung-6→7 V&V upgrade.

Future cycles will extend to Misra1a (single-exponential saturation — needs a
constrained constant+exponential model), the Gauss1/2/3 multi-Gaussian
problems (already covered by spectrafit's catalog), and Bennett5 (a hard
power-law problem that stresses the trust-region step machinery).
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


# ---------------------------------------------------------------------------
# NIST StRD Eckerle4 problem definition (verbatim from itl.nist.gov)
# ---------------------------------------------------------------------------
#
# Model:  y = (b1 / b2) · exp[ −0.5 · ((x − b3) / b2)² ]
#
# Difficulty: Higher.  35 observations, 3 free parameters.
#
# The parameterization is non-standard for a Gaussian — the prefactor
# `b1 / b2` makes b1 an *area-like* scale rather than the peak height.
# Spectrafit-core's Gaussian uses peak-height amplitude (`A · exp(...)`),
# so the parameter mapping is:
#
#     A_spectrafit  =  b1 / b2          (peak height at x = b3)
#     c_spectrafit  =  b3               (center)
#     σ_spectrafit  =  b2               (standard deviation)
#
# After fitting, the recovered (A, c, σ) project back to the NIST
# parameterization for comparison against certified values.
# ---------------------------------------------------------------------------

# Certified parameter values + their certified 1σ standard errors.
NIST_B1 = 1.5543827178e0
NIST_B1_STDERR = 1.5408051163e-02
NIST_B2 = 4.0888321754e0
NIST_B2_STDERR = 4.6803020753e-02
NIST_B3 = 4.5154121844e02
NIST_B3_STDERR = 4.6800518816e-02

# Certified residual sum of squares (Σ residual²).
NIST_RSS = 1.4635887487e-03

# All 35 (x, y) data points.
_DATA = np.array(
    [
        (400.0, 0.0001575),
        (405.0, 0.0001699),
        (410.0, 0.0002350),
        (415.0, 0.0003102),
        (420.0, 0.0004917),
        (425.0, 0.0008710),
        (430.0, 0.0017418),
        (435.0, 0.0046400),
        (436.5, 0.0065895),
        (438.0, 0.0097302),
        (439.5, 0.0149002),
        (441.0, 0.0237310),
        (442.5, 0.0401683),
        (444.0, 0.0712559),
        (445.5, 0.1264458),
        (447.0, 0.2073413),
        (448.5, 0.2902366),
        (450.0, 0.3445623),
        (451.5, 0.3698049),
        (453.0, 0.3668534),
        (454.5, 0.3106727),
        (456.0, 0.2078154),
        (457.5, 0.1164354),
        (459.0, 0.0616764),
        (460.5, 0.0337200),
        (462.0, 0.0194023),
        (463.5, 0.0117831),
        (465.0, 0.0074357),
        (470.0, 0.0022732),
        (475.0, 0.0008800),
        (480.0, 0.0004579),
        (485.0, 0.0002345),
        (490.0, 0.0001586),
        (495.0, 0.0001143),
        (500.0, 0.0000710),
    ],
    dtype=np.float64,
)
X_NIST = _DATA[:, 0]
Y_NIST = _DATA[:, 1]
N_OBS = X_NIST.size
N_PARAMS = 3
DOF = N_OBS - N_PARAMS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spectrafit_to_nist(amp: float, center: float, sigma: float) -> tuple[float, float, float]:
    """Project spectrafit (A, c, σ) back to NIST (b1, b2, b3)."""
    return amp * sigma, sigma, center


def _build_eckerle4_graph(start: str) -> FitGraph:
    """Build the spectrafit Gaussian for the Eckerle4 problem.

    NIST publishes TWO starting guess sets:
    - "start1" = (1.0, 10.0, 500.0)  — further from truth
    - "start2" = (1.5, 5.0, 450.0)   — closer to truth

    The b1/b2 → spectrafit-A mapping turns start1 into amplitude = 0.1 (truth
    ≈ 0.38) and start2 into amplitude = 0.3.
    """
    if start == "start1":
        a0, c0, s0 = 1.0 / 10.0, 500.0, 10.0
    elif start == "start2":
        a0, c0, s0 = 1.5 / 5.0, 450.0, 5.0
    else:  # pragma: no cover - dev guard
        raise ValueError(f"unknown start preset {start!r}")
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="g",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=a0, min=1e-6),
                    "center": Parameter(value=c0),
                    "sigma": Parameter(value=s0, min=1e-3),
                },
            )
        ]
    )


def _measurement() -> MeasurementData:
    return MeasurementData(x=X_NIST.tolist(), y=Y_NIST.tolist())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("start", ["start1", "start2"])
def test_eckerle4_recovers_nist_certified_parameters(start: str) -> None:
    """From either NIST starting guess, spectrafit recovers the certified
    Eckerle4 parameters to within 1e-3 relative.

    Eckerle4 is NIST "Higher" difficulty — the peak is narrow (σ ≈ 4) in a
    wide window (x ∈ [400, 500]) with a fast-decaying exponential lineshape.
    LM convergence from start1 in particular requires the trust-region step
    machinery to handle a near-singular initial Jacobian (the peak is too
    narrow to be picked up at amplitude=0.1 / sigma=10).
    """
    opts = FitOptions(solver="lm", max_iterations=5000, tolerance=1e-12)
    result = fit(_build_eckerle4_graph(start), _measurement(), opts)
    assert result.success is True, (
        f"Eckerle4 ({start}) did not converge: {result.message}"
    )

    amp = result.params["g.amplitude"].value
    center = result.params["g.center"].value
    sigma = result.params["g.sigma"].value
    b1_recovered, b2_recovered, b3_recovered = _spectrafit_to_nist(amp, center, sigma)

    rel_b1 = abs(b1_recovered - NIST_B1) / NIST_B1
    rel_b2 = abs(b2_recovered - NIST_B2) / NIST_B2
    rel_b3 = abs(b3_recovered - NIST_B3) / NIST_B3
    assert rel_b1 < 1e-3, f"b1: recovered {b1_recovered:.6e}, certified {NIST_B1:.6e}, rel {rel_b1:.2e}"
    assert rel_b2 < 1e-3, f"b2: recovered {b2_recovered:.6e}, certified {NIST_B2:.6e}, rel {rel_b2:.2e}"
    assert rel_b3 < 1e-6, f"b3: recovered {b3_recovered:.6e}, certified {NIST_B3:.6e}, rel {rel_b3:.2e}"


def test_eckerle4_rss_matches_nist_certified() -> None:
    """The fitted residual sum of squares matches NIST's certified RSS.

    Certified value: 1.4635887487e-03 (10 significant figures).
    Required agreement: 1e-4 relative (= 4+ significant figures), which is
    the floor below which floating-point accumulation order genuinely
    differs between solvers.
    """
    opts = FitOptions(solver="lm", max_iterations=5000, tolerance=1e-12)
    result = fit(_build_eckerle4_graph("start2"), _measurement(), opts)
    assert result.success is True

    # `result.chi2` is Σ residual² in spectrafit's unweighted formulation,
    # equivalent to NIST's RSS.
    rss_recovered = float(result.chi2)
    rel = abs(rss_recovered - NIST_RSS) / NIST_RSS
    assert rel < 1e-4, (
        f"RSS: recovered {rss_recovered:.10e}, certified {NIST_RSS:.10e}, rel {rel:.2e}"
    )


def test_eckerle4_stderr_matches_nist_certified() -> None:
    """Per-parameter stderrs match NIST's certified 1σ within 15 %.

    For b2 = σ_spectrafit and b3 = c_spectrafit the mapping is 1-to-1, so the
    `result.params[name].stderr` value compares directly. For b1 = A·σ the
    proper error propagation uses the full covariance cross-term, addressed
    via `result.covariance_param_order` (Cycle 21 / 16.F fix):

        σ_b1² = σ² · Var(A) + A² · Var(σ) + 2·A·σ · Cov(A, σ)

    where Var(A) = cov[idx_A, idx_A], Var(σ) = cov[idx_σ, idx_σ], and
    Cov(A, σ) = cov[idx_A, idx_σ].  For a Gaussian fit the cross-term is
    negative (A and σ trade off), so including it tightens σ_b1 and allows
    a 15 % envelope rather than the factor-of-3 used before this fix.
    """
    opts = FitOptions(solver="lm", max_iterations=5000, tolerance=1e-12)
    result = fit(_build_eckerle4_graph("start2"), _measurement(), opts)
    assert result.success is True

    amp_pr = result.params["g.amplitude"]
    center_pr = result.params["g.center"]
    sigma_pr = result.params["g.sigma"]
    assert amp_pr.stderr is not None
    assert center_pr.stderr is not None
    assert sigma_pr.stderr is not None

    # Cycle 21: covariance_param_order is now populated — use it to index cov.
    order = result.covariance_param_order
    assert order is not None, "covariance_param_order must be set after Cycle 21 fix"
    assert result.covariance is not None, "covariance matrix must be present"

    cov = result.covariance
    idx_amp = order.index("g.amplitude")
    idx_sigma = order.index("g.sigma")

    # b2 (= σ) and b3 (= c) read directly from per-param stderrs.
    sigma_b2_recovered = float(sigma_pr.stderr)
    sigma_b3_recovered = float(center_pr.stderr)

    # b1 = A·σ via full covariance propagation (cross-term included).
    amp = float(amp_pr.value)
    sigma = float(sigma_pr.value)
    var_amp = float(cov[idx_amp][idx_amp])
    var_sig = float(cov[idx_sigma][idx_sigma])
    cov_amp_sig = float(cov[idx_amp][idx_sigma])
    var_b1 = (
        sigma * sigma * var_amp
        + amp * amp * var_sig
        + 2.0 * amp * sigma * cov_amp_sig
    )
    # Guard: numerical noise can push var_b1 slightly negative on near-perfect
    # fits; clamp to zero before sqrt.
    sigma_b1_recovered = math.sqrt(max(var_b1, 0.0))

    # Envelopes: all three at 15 % now that the cross-term is correct.
    for name, recovered, certified in (
        ("b1", sigma_b1_recovered, NIST_B1_STDERR),
        ("b2", sigma_b2_recovered, NIST_B2_STDERR),
        ("b3", sigma_b3_recovered, NIST_B3_STDERR),
    ):
        ratio = recovered / certified
        assert 0.85 <= ratio <= 1.15, (
            f"{name}: recovered stderr {recovered:.6e} vs NIST certified "
            f"{certified:.6e} (ratio {ratio:.4f}, expected within [0.85, 1.15])"
        )


def test_eckerle4_reduced_chi2_is_close_to_certified_per_dof() -> None:
    """Reduced χ² (= RSS/DOF) matches the certified value within 1e-4 relative.

    Cross-check on result.reduced_chi2: a different code path than chi2 ÷ dof,
    so it independently verifies the DOF count + the reduced-χ² formula.
    """
    opts = FitOptions(solver="lm", max_iterations=5000, tolerance=1e-12)
    result = fit(_build_eckerle4_graph("start2"), _measurement(), opts)
    assert result.success is True

    certified_red_chi2 = NIST_RSS / DOF
    recovered = float(result.reduced_chi2)
    rel = abs(recovered - certified_red_chi2) / certified_red_chi2
    assert rel < 1e-4, (
        f"reduced χ²: recovered {recovered:.10e}, certified {certified_red_chi2:.10e}, "
        f"rel {rel:.2e}"
    )
    # Sanity: the test scaffold's DOF should agree with the result's reported dof.
    assert result.dof == DOF


def test_eckerle4_data_is_well_formed() -> None:
    """Smoke check on the embedded NIST fixture: 35 points, monotonic x, no NaN."""
    assert N_OBS == 35
    assert N_PARAMS == 3
    assert DOF == 32
    assert np.all(np.isfinite(X_NIST))
    assert np.all(np.isfinite(Y_NIST))
    # Strictly monotonic ascending x.
    assert np.all(np.diff(X_NIST) > 0)
    # Peak y is between 0.36 and 0.38 at x ≈ 451 (verifies we didn't fat-finger).
    peak_idx = int(np.argmax(Y_NIST))
    assert 449.0 <= X_NIST[peak_idx] <= 453.0
    assert 0.35 < Y_NIST[peak_idx] < 0.38
    # math.isclose check on a known integer-ish quantity.
    assert math.isclose(NIST_B3, 451.5412, rel_tol=1e-4)
