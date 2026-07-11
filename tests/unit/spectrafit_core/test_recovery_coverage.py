"""Synthetic-recovery coverage statistic (ground-truth Phase 2).

The canonical V&V check for fitting code is *not* "does it recover the truth on
one noiseless example" — that's a happy-path point check. It is "are the reported
1σ uncertainty bars honest?" Across many fits of noisy synthetic data drawn from
a known truth + known noise model, three properties must hold:

1. **No bias.** The empirical mean of recovered parameters tracks the truth
   (within stderr/√N of the trial count).
2. **Empirical std ≈ reported stderr.** The width of the recovered-parameter
   distribution matches what each fit reports as ``ParameterResult.stderr``.
3. **Coverage ≈ 68 %.** The 1σ stderr bar contains the truth in ~68 % of
   trials (the binomial 95 % CI at N=100, p=0.68 is [0.586, 0.766]).

Without (2) and (3), every downstream "result is x ± y" report is misleading
even when (1) holds. This is the rung-4-to-5 ground-truth promotion for the
fitting layer (rung 4 = metamorphic on Jacobians; rung 5 = synthetic recovery
with correct coverage and quantified UQ).

The test is fast enough to keep in the default suite (~2 s for N=100 on a clean
Gaussian); the cost is paid once per CI run and pays back as a permanent
defect-detector for any future change to the covariance-from-Jacobian path.
"""

from __future__ import annotations

import numpy as np
import pytest

from spectrafit_core import (
    FitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)


def _gaussian_y(x: np.ndarray, a: float, c: float, sigma: float) -> np.ndarray:
    return a * np.exp(-0.5 * ((x - c) / sigma) ** 2)


def _build_graph() -> FitGraph:
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="peak",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=4.5, min=0.0),
                    "center": Parameter(value=1.8),
                    "sigma": Parameter(value=0.55, min=1e-3),
                },
            )
        ]
    )


def test_recovery_coverage_statistic_single_gaussian() -> None:
    """1σ stderr bar covers the truth ~68 % of the time across MC trials.

    Pins three V&V properties at once: no bias, honest error bars,
    correct coverage. A regression in the covariance-from-Jacobian path —
    a wrong scale factor, a missing √(chi²/dof) multiplier, a wrong
    Jacobian — would shift the coverage statistic outside the 95 % binomial
    CI for the 100-trial run.
    """
    rng = np.random.default_rng(seed=20260609)
    a_true, c_true, s_true = 5.0, 2.0, 0.5
    noise_sigma = 0.05  # ~1 % of peak
    n_trials = 100
    x = np.linspace(-1.0, 5.0, 64)
    y_clean = _gaussian_y(x, a_true, c_true, s_true)

    recovered_a: list[float] = []
    stderr_a: list[float] = []
    cover_a = 0
    cover_c = 0
    cover_s = 0
    recovered_c: list[float] = []
    recovered_s: list[float] = []
    n_successes = 0

    for _ in range(n_trials):
        y_noisy = y_clean + rng.normal(0.0, noise_sigma, size=len(x))
        data = MeasurementData(x=x.tolist(), y=y_noisy.tolist())
        result = fit(_build_graph(), data)
        if not result.success:
            continue
        n_successes += 1
        amp = result.params["peak.amplitude"]
        cen = result.params["peak.center"]
        sig = result.params["peak.sigma"]
        assert amp.stderr is not None
        assert cen.stderr is not None
        assert sig.stderr is not None
        recovered_a.append(amp.value)
        recovered_c.append(cen.value)
        recovered_s.append(sig.value)
        stderr_a.append(amp.stderr)
        if abs(amp.value - a_true) <= amp.stderr:
            cover_a += 1
        if abs(cen.value - c_true) <= cen.stderr:
            cover_c += 1
        if abs(sig.value - s_true) <= sig.stderr:
            cover_s += 1

    # At least 95% of trials must converge on this clean problem.
    assert n_successes >= 95, f"only {n_successes}/{n_trials} fits converged"

    # (1) No bias: empirical mean → truth within 5σ of the per-trial stderr.
    # 5σ over the standard error of the mean (stderr/√N) is a generous bound
    # that catches systematic bias without flaking on the MC noise floor.
    mean_a = float(np.mean(recovered_a))
    mean_c = float(np.mean(recovered_c))
    mean_s = float(np.mean(recovered_s))
    sem_a = float(np.mean(stderr_a)) / np.sqrt(n_successes)
    assert abs(mean_a - a_true) < 5.0 * sem_a, (
        f"amplitude bias: mean={mean_a:.5f}, truth={a_true}, SEM={sem_a:.5f}"
    )
    # Looser bounds on c, s — they couple via the Gaussian's Jacobian, so
    # use stderr directly rather than SEM (still catches gross bias).
    assert abs(mean_c - c_true) < 5.0 * np.std(recovered_c, ddof=1) / np.sqrt(n_successes)
    assert abs(mean_s - s_true) < 5.0 * np.std(recovered_s, ddof=1) / np.sqrt(n_successes)

    # (2) Empirical std ≈ reported stderr (within 35 % at N=100). The expected
    # ratio is 1; the 95 % CI of empirical_std/true_std at N=100 is about
    # [0.88, 1.15], plus model-misspecification slack from the rust covariance
    # path. The 35 % envelope is loose enough to be a permanent gate, tight
    # enough to catch a 2× or 3× scale factor mistake.
    empirical_std_a = float(np.std(recovered_a, ddof=1))
    mean_reported_a = float(np.mean(stderr_a))
    rel = abs(empirical_std_a - mean_reported_a) / mean_reported_a
    assert rel < 0.35, (
        f"empirical std {empirical_std_a:.5f} disagrees with reported stderr "
        f"{mean_reported_a:.5f} by {rel:.0%}"
    )

    # (3) Coverage: 1σ bar contains truth in ~68 % of trials.
    # Binomial 95 % CI at N=100, p=0.68 is [58.6, 76.6]. Use a slightly
    # wider envelope [50, 82] to absorb cross-param correlations and avoid
    # CI flakes — still catches a coverage collapse (e.g., 0 % or 100 %).
    for param_name, cover in (("amplitude", cover_a), ("center", cover_c), ("sigma", cover_s)):
        frac = cover / n_successes
        assert 0.50 <= frac <= 0.82, (
            f"{param_name} coverage {frac:.0%} outside [50%, 82%]; "
            f"expected ~68 % for honest 1σ bars"
        )


def test_recovery_coverage_uses_jacobian_correctly() -> None:
    """A reduced-χ² ≈ 1 fit must report a non-zero stderr proportional to noise.

    Sanity check on the covariance path: if we increase the noise by a factor
    of 3, the reported stderr should grow by a comparable factor. Catches a
    "stderr is hard-coded / unrelated to chi²" regression.
    """
    a_true, c_true, s_true = 5.0, 2.0, 0.5
    x = np.linspace(-1.0, 5.0, 64)
    y_clean = _gaussian_y(x, a_true, c_true, s_true)

    def _run(noise_sigma: float, seed_offset: int) -> float:
        rng_local = np.random.default_rng(seed=42 + seed_offset)
        stderrs: list[float] = []
        for _ in range(20):
            y_noisy = y_clean + rng_local.normal(0.0, noise_sigma, size=len(x))
            data = MeasurementData(x=x.tolist(), y=y_noisy.tolist())
            result = fit(_build_graph(), data)
            if not result.success:
                continue
            amp = result.params["peak.amplitude"]
            if amp.stderr is not None:
                stderrs.append(amp.stderr)
        assert stderrs, "no successful fits to evaluate stderr"
        return float(np.mean(stderrs))

    stderr_low = _run(noise_sigma=0.02, seed_offset=0)
    stderr_high = _run(noise_sigma=0.06, seed_offset=1)

    # Stderr should scale ~ linearly with noise — expected ratio ≈ 3 ± wide
    # noise band for N=20 trials each.
    ratio = stderr_high / stderr_low
    assert 1.5 < ratio < 5.0, (
        f"stderr ratio {ratio:.2f} not linear in noise (expected ~3); "
        f"low={stderr_low:.5f}, high={stderr_high:.5f}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
