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

import math
import zlib

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
            ),
        ],
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
    assert abs(mean_c - c_true) < 5.0 * np.std(recovered_c, ddof=1) / np.sqrt(
        n_successes,
    )
    assert abs(mean_s - s_true) < 5.0 * np.std(recovered_s, ddof=1) / np.sqrt(
        n_successes,
    )

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
    for param_name, cover in (
        ("amplitude", cover_a),
        ("center", cover_c),
        ("sigma", cover_s),
    ):
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


# ---------------------------------------------------------------------------
# Off-the-happy-path coverage sweep: asymmetric kernels x {lm, trf, varpro}
# ---------------------------------------------------------------------------
#
# The single-Gaussian/LM test above is the strongest signal (N=100, clean
# kernel, well-conditioned problem). Nominal error bars most often break
# exactly where that case does not look: asymmetric kernels (whose sampling
# distribution over noisy refits need not be Gaussian even when the reported
# stderr assumes it is) and VarPro (whose linear amplitude comes out of a
# projection, not the same Jacobian/covariance path as the nonlinear
# parameters). This section extends the same three-property check — no bias,
# empirical std $\approx$ reported stderr, ~68 % coverage — across kernels
# and solvers instead of replacing the clean-Gaussian case.

# Ground truth per kernel, in the same units/scale as the clean-Gaussian case
# above (amplitude ~5, sigma ~0.5, x in [-1, 5]) so noise_sigma=0.05 (~1 % of
# peak) means the same thing everywhere.
_KERNEL_TRUTHS: dict[str, dict[str, float]] = {
    "gaussian": {"amplitude": 5.0, "center": 2.0, "sigma": 0.5},
    "skewed_gaussian": {"amplitude": 5.0, "center": 2.0, "sigma": 0.6, "gamma": 2.0},
    "doniach_sunjic": {"amplitude": 5.0, "center": 2.0, "sigma": 0.5, "gamma": 0.3},
}

# VarPro requires graph separability (crates/spectrafit-varpro/src/lib.rs,
# `SEPARABLE_MODEL_TYPES`); of the three kernels exercised here only
# "gaussian" qualifies. `skewed_gaussian` and `doniach_sunjic` are named
# explicitly in that module's own doc-comment as non-separable, and
# `solver="varpro"` against them raises
# ``ValueError("solver='varpro' requested but graph is not separable")``
# (crates/spectrafit-solver/src/error.rs::VarproNotSeparable) before any
# fit is attempted — a structural precondition, not a statistical outcome, so
# `_COVERAGE_CASES` below marks those two combinations `pytest.mark.skip`
# rather than `pytest.mark.xfail`.


def _skewed_gaussian_y(
    x: np.ndarray,
    a: float,
    c: float,
    sigma: float,
    gamma: float,
) -> np.ndarray:
    r"""Skewed Gaussian, mirroring ``skewed_gaussian.rs::eval`` exactly.

    $A \cdot e^{-\frac{1}{2}\left(\frac{x-c}{\sigma}\right)^2} \cdot
    \left(1 + \mathrm{erf}(\beta (x - c))\right)$, with
    $\beta = \gamma / (\sigma \sqrt{2})$.
    """
    dx = x - c
    g = np.exp(-0.5 * (dx / sigma) ** 2)
    beta = gamma / (sigma * math.sqrt(2.0))
    erf_term = np.array([math.erf(v) for v in beta * dx])
    return a * g * (1.0 + erf_term)


def _doniach_sunjic_y(
    x: np.ndarray,
    a: float,
    c: float,
    sigma: float,
    gamma: float,
) -> np.ndarray:
    r"""Doniach-Sunjic lineshape, mirroring ``doniach.rs::eval`` exactly.

    $A \cos\!\left[\frac{\pi\gamma}{2} + (1-\gamma)\arctan(u)\right] /
    (1+u^2)^{(1-\gamma)/2}$, with $u = (x-c)/\sigma$.
    """
    u = (x - c) / sigma
    num = np.cos(math.pi / 2.0 * gamma + (1.0 - gamma) * np.arctan(u))
    den = (1.0 + u**2) ** ((1.0 - gamma) / 2.0)
    return a * num / den


def _clean_y(kernel: str, x: np.ndarray, truths: dict[str, float]) -> np.ndarray:
    """Evaluate the noiseless truth curve for one of the swept kernels."""
    match kernel:
        case "gaussian":
            return _gaussian_y(x, truths["amplitude"], truths["center"], truths["sigma"])
        case "skewed_gaussian":
            return _skewed_gaussian_y(
                x,
                truths["amplitude"],
                truths["center"],
                truths["sigma"],
                truths["gamma"],
            )
        case "doniach_sunjic":
            return _doniach_sunjic_y(
                x,
                truths["amplitude"],
                truths["center"],
                truths["sigma"],
                truths["gamma"],
            )
        case _:
            raise ValueError(f"unsupported kernel: {kernel}")


def _build_graph_for_kernel(kernel: str, truths: dict[str, float]) -> FitGraph:
    """Build a single-node ``FitGraph`` of ``kernel`` initialised at truth."""
    match kernel:
        case "gaussian":
            model_type = ModelType.GAUSSIAN
        case "skewed_gaussian":
            model_type = ModelType.SKEWED_GAUSSIAN
        case "doniach_sunjic":
            model_type = ModelType.DONIACH
        case _:
            raise ValueError(f"unsupported kernel: {kernel}")

    parameters = {
        "amplitude": Parameter(value=truths["amplitude"], min=0.0),
        "center": Parameter(value=truths["center"]),
        "sigma": Parameter(value=truths["sigma"], min=1e-3),
    }
    if "gamma" in truths:
        parameters["gamma"] = Parameter(value=truths["gamma"])

    return FitGraph(
        nodes=[
            ModelNodeSpec(id="peak", model_type=model_type, parameters=parameters),
        ],
    )


def _coverage_envelope(n: int, p: float = 0.68, z: float = 3.0) -> tuple[float, float]:
    r"""Return a $z\sigma$ acceptance band around binomial coverage $p$ at size $n$.

    $z=3$ is deliberately wider than the raw 95 % ($z \approx 1.96$) CI to
    absorb cross-parameter correlation and Monte-Carlo noise across many
    (kernel, solver) combinations — at $n=100$ this reproduces the
    hand-picked [50 %, 82 %] envelope used by
    ``test_recovery_coverage_statistic_single_gaussian`` above.
    """
    se = math.sqrt(p * (1.0 - p) / n)
    return max(0.0, p - z * se), min(1.0, p + z * se)


class _CoverageStats:
    """Per-trial accumulator for one (kernel, solver) synthetic-recovery sweep."""

    def __init__(self, truths: dict[str, float]) -> None:
        self.truths = truths
        self.param_names = list(truths.keys())
        self.recovered: dict[str, list[float]] = {p: [] for p in self.param_names}
        self.stderrs: dict[str, list[float]] = {p: [] for p in self.param_names}
        self.cover: dict[str, int] = dict.fromkeys(self.param_names, 0)
        self.n_successes = 0

    def record(self, param_values: dict[str, float], param_stderrs: dict[str, float]) -> None:
        self.n_successes += 1
        for p in self.param_names:
            self.recovered[p].append(param_values[p])
            self.stderrs[p].append(param_stderrs[p])
            if abs(param_values[p] - self.truths[p]) <= param_stderrs[p]:
                self.cover[p] += 1

    def coverage(self, param: str) -> float:
        return self.cover[param] / self.n_successes if self.n_successes else float("nan")


def _run_coverage_sweep(
    kernel: str,
    solver: str,
    *,
    n_trials: int,
    seed: int,
    noise_sigma: float = 0.05,
) -> _CoverageStats:
    """Run ``n_trials`` noisy refits of ``kernel`` under ``solver`` and collect stats."""
    truths = _KERNEL_TRUTHS[kernel]
    rng = np.random.default_rng(seed=seed)
    x = np.linspace(-1.0, 5.0, 64)
    y_clean = _clean_y(kernel, x, truths)
    stats = _CoverageStats(truths)

    for _ in range(n_trials):
        y_noisy = y_clean + rng.normal(0.0, noise_sigma, size=len(x))
        data = MeasurementData(x=x.tolist(), y=y_noisy.tolist())
        result = fit(
            _build_graph_for_kernel(kernel, truths),
            data,
            options=FitOptions(solver=solver),
        )
        if not result.success:
            continue
        values: dict[str, float] = {}
        stderrs: dict[str, float] = {}
        complete = True
        for p in stats.param_names:
            pr = result.params[f"peak.{p}"]
            if pr.stderr is None:
                complete = False
                break
            values[p] = pr.value
            stderrs[p] = pr.stderr
        if complete:
            stats.record(values, stderrs)

    return stats


# Sweep sample size. The flagship clean-Gaussian/LM case above stays at its
# original N=100. Here, 7 (kernel, solver) combinations actually run (the 2
# non-separable-varpro combinations are skipped, see
# `_VARPRO_SEPARABLE_KERNELS`); at ~20 ms/fit that is 7 x 40 x 20 ms ~= 5.6 s
# added to the default suite, which stays "keep the default-suite cost sane."
_SWEEP_N_TRIALS = 40
_SWEEP_MIN_SUCCESS_FRACTION = 0.90


# Explicit (kernel, solver) case list rather than two stacked `parametrize`
# decorators, so a per-case annotation can sit right next to the case it
# annotates: the two structurally-inapplicable combinations (VarPro on a
# non-separable kernel) carry a plain skip, and — until 2026-08-21 — the
# then-broken gaussian/varpro combination carried a `strict=True` xfail with
# its exact measured number. That xfail is gone; see the note on the case.
_COVERAGE_CASES = [
    pytest.param("gaussian", "lm", id="gaussian-lm"),
    pytest.param("gaussian", "trf", id="gaussian-trf"),
    # FIXED 2026-08-21 (was a strict xfail): VarPro wrote the covariance
    # diagonal back in its own internal solve order (nonlinear alpha first,
    # then the linear amplitude coefficients) while the matrix itself is
    # indexed by `CompiledGraph::free_keys` (amplitude, center, sigma). That
    # single 0<->1 index permutation handed amplitude the center error bar and
    # vice versa, which is why amplitude read 12.5% (5/40) and center read
    # 100% (40/40) in the same run — one swap, both symptoms. Post-fix at
    # N=40, seed=crc32("gaussian:varpro"): amplitude 65% (26/40), center 68%
    # (27/40), sigma 68% (27/40), all inside the [46%, 90%] envelope.
    pytest.param("gaussian", "varpro", id="gaussian-varpro"),
    pytest.param("skewed_gaussian", "lm", id="skewed_gaussian-lm"),
    pytest.param("skewed_gaussian", "trf", id="skewed_gaussian-trf"),
    pytest.param(
        "skewed_gaussian",
        "varpro",
        marks=pytest.mark.skip(
            reason=(
                "solver='varpro' requires a separable graph "
                "(spectrafit-varpro::SEPARABLE_MODEL_TYPES); skewed_gaussian is "
                "explicitly named as non-separable there and raises "
                "ValueError('solver=\\'varpro\\' requested but graph is not "
                "separable') before any fit runs — a structural precondition, "
                "not a statistical outcome to xfail."
            ),
        ),
        id="skewed_gaussian-varpro",
    ),
    pytest.param("doniach_sunjic", "lm", id="doniach_sunjic-lm"),
    pytest.param("doniach_sunjic", "trf", id="doniach_sunjic-trf"),
    pytest.param(
        "doniach_sunjic",
        "varpro",
        marks=pytest.mark.skip(
            reason=(
                "solver='varpro' requires a separable graph "
                "(spectrafit-varpro::SEPARABLE_MODEL_TYPES); doniach_sunjic is "
                "not in that list and raises ValueError('solver=\\'varpro\\' "
                "requested but graph is not separable') before any fit runs — "
                "a structural precondition, not a statistical outcome to xfail."
            ),
        ),
        id="doniach_sunjic-varpro",
    ),
]


@pytest.mark.parametrize(("kernel", "solver"), _COVERAGE_CASES)
def test_coverage_holds_off_the_happy_path(kernel: str, solver: str) -> None:
    """1-sigma bars must contain truth ~68% of the time for asymmetric kernels too.

    Extends the clean-Gaussian/LM coverage guarantee across
    ``skewed_gaussian``, ``doniach_sunjic`` and the ``trf``/``varpro``
    solvers. Nominal error bars most often break exactly here: an asymmetric
    kernel's noisy-refit distribution need not be Gaussian even when the
    reported stderr assumes it is, and VarPro reaches the same optimum by a
    different route (linear amplitudes eliminated by projection), so its
    covariance write-back is a separate code path from LM's. See
    ``_COVERAGE_CASES`` for the permutation defect that used to make
    ``gaussian/varpro`` a ``strict`` xfail, and for why the two
    non-separable-kernel/varpro cases are skipped rather than xfailed.
    """
    # zlib.crc32, not the builtin hash(): str hashing is salted per-process
    # (PYTHONHASHSEED) unless disabled, which would make this seed — and
    # therefore every measured coverage number pinned against it — vary from
    # run to run.
    seed = zlib.crc32(f"{kernel}:{solver}".encode())
    stats = _run_coverage_sweep(kernel, solver, n_trials=_SWEEP_N_TRIALS, seed=seed)

    min_successes = math.ceil(_SWEEP_MIN_SUCCESS_FRACTION * _SWEEP_N_TRIALS)
    assert stats.n_successes >= min_successes, (
        f"[{kernel}/{solver}] only {stats.n_successes}/{_SWEEP_N_TRIALS} fits converged"
    )

    lo, hi = _coverage_envelope(stats.n_successes)
    for param in stats.param_names:
        frac = stats.coverage(param)
        assert lo <= frac <= hi, (
            f"[{kernel}/{solver}] {param} coverage {frac:.0%} outside "
            f"[{lo:.0%}, {hi:.0%}]; expected ~68% for honest 1-sigma bars "
            f"(n_successes={stats.n_successes})"
        )


# ---------------------------------------------------------------------------
# VarPro amplitude coverage: the linear-projection stderr path
# ---------------------------------------------------------------------------


def test_varpro_amplitude_coverage() -> None:
    r"""VarPro's amplitude stderr must also give ~68% 1-$\sigma$ coverage.

    Was a ``strict`` xfail until 2026-08-21, on the reading that VarPro's
    projected amplitude estimate simply never travelled through the shared
    Jacobian-derived covariance path. That reading is superseded. The
    amplitude *does* travel that path; VarPro merely wrote the covariance
    diagonal back in its own internal solve order (nonlinear $\alpha$ first,
    then the linear coefficients) against a matrix indexed by
    ``CompiledGraph::free_keys`` (amplitude, center, sigma). One 0-to-1 index
    permutation accounts for *both* prior symptoms at once: amplitude read
    11% (11/100) because it was shown ``center``'s much tighter bar, and
    ``center`` read 100% because it was shown ``amplitude``'s much wider one.
    Fixed in ``crates/spectrafit-varpro/src/solver.rs::fill_parameter_stderr``.

    Post-fix at N=100, seed=20260821 (all 100 fits converged): amplitude 68%
    (68/100), center 78% (78/100), sigma 56% (56/100) — every one inside the
    binomial-derived [54%, 82%] band. Uses the same N=100 as the flagship
    clean-Gaussian/LM test since only one (kernel, solver) pair runs here.
    """
    stats = _run_coverage_sweep("gaussian", "varpro", n_trials=100, seed=20260821)

    assert stats.n_successes >= 95, f"only {stats.n_successes}/100 varpro fits converged"

    lo, hi = _coverage_envelope(stats.n_successes)
    frac = stats.coverage("amplitude")
    assert lo <= frac <= hi, (
        f"varpro amplitude coverage {frac:.0%} outside [{lo:.0%}, {hi:.0%}]; "
        f"expected ~68% for honest 1-sigma bars (n_successes={stats.n_successes})"
    )


# ---------------------------------------------------------------------------
# VarPro stderr indexing: the permutation itself, not one of its symptoms
# ---------------------------------------------------------------------------


def test_varpro_stderr_vector_matches_lm() -> None:
    r"""VarPro's per-parameter $\sigma$ must land on the same parameters as LM's.

    The defect this pins was an index permutation, not a scale error: varpro
    reported [0.004433, 0.011324, 0.004433] where lm and trf both reported
    [0.011324, 0.004433, 0.004433] for (amplitude, center, sigma). A coverage
    assertion alone would also pass under a mere rescale, so the coverage
    tests above cannot stand in for this one.
    """
    rng = np.random.default_rng(seed=20260821)
    x = np.linspace(-1.0, 5.0, 400)
    y = _gaussian_y(x, 5.0, 2.0, 0.5) + rng.normal(0.0, 0.08, size=x.size)
    data = MeasurementData(x=x.tolist(), y=y.tolist())

    names = ("amplitude", "center", "sigma")
    results = {
        solver: fit(_build_graph(), data, options=FitOptions(solver=solver))
        for solver in ("lm", "trf", "varpro")
    }
    for solver, result in results.items():
        assert result.success, f"{solver} must converge on a clean single Gaussian"

    values = {
        solver: [result.params[f"peak.{n}"].value for n in names]
        for solver, result in results.items()
    }
    stderrs: dict[str, list[float]] = {}
    for solver, result in results.items():
        vec: list[float] = []
        for n in names:
            err = result.params[f"peak.{n}"].stderr
            assert err is not None, f"{solver} left peak.{n}.stderr unreported"
            vec.append(err)
        stderrs[solver] = vec

    # The fitted values agreeing is what makes any stderr disagreement
    # diagnostic: all three solvers must have found the *same* optimum, so a
    # differing error bar cannot be excused as "a different minimum".
    for solver in ("trf", "varpro"):
        np.testing.assert_allclose(
            values[solver],
            values["lm"],
            rtol=1e-4,
            err_msg=f"{solver} found a different optimum than lm; stderr comparison is moot",
        )

    # rtol=0.25, deliberately not tighter: the upstream varpro crate (v0.14.0)
    # uses the Kaufman (1975) Jacobian approximation, so VarPro's covariance is
    # approximate by construction even once correctly indexed, and exact
    # equality with LM is not expected. It is still far tighter than needed to
    # catch the defect — the swapped entries differ by ~2.6x (a relative error
    # of ~1.6), so anything below ~1.5 catches a swap comfortably.
    np.testing.assert_allclose(
        stderrs["trf"],
        stderrs["lm"],
        rtol=0.25,
        err_msg=f"trf stderr vector {stderrs['trf']} disagrees with lm {stderrs['lm']}",
    )
    np.testing.assert_allclose(
        stderrs["varpro"],
        stderrs["lm"],
        rtol=0.25,
        err_msg=(
            f"varpro stderr vector {stderrs['varpro']} disagrees with lm "
            f"{stderrs['lm']} — check for an index permutation in "
            "spectrafit-varpro::fill_parameter_stderr, not a scale factor"
        ),
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
