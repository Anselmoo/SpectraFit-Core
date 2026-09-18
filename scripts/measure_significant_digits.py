#!/usr/bin/env python3
r"""Monte-Carlo arithmetic estimate of significant digits in post-fit statistics.

Rung 3 of the project's credibility ladder requires *measured* significant
digits for reported quantities, not an assumed float64 default. No
stochastic-arithmetic tool (Shaman, CADNA, Verificarlo) is installed
anywhere in this repository, and none of the three would install without
recompiling either the numeric core (Shaman, a header-only C++ library) or
the whole Rust/C toolchain through an LLVM pass (Verificarlo) -- disproportionate
for a first number and a real risk to a working build. This script
implements the project's own lightweight **Monte-Carlo Arithmetic (MCA)**
shim instead: perturb every input datum by one unit in the last place (ulp)
in a random direction via :func:`numpy.nextafter`, refit from the same
initial guess, repeat ``N=50`` times, and for every reported quantity $q$
compute

$$
s = -\log_{10}\!\left(\frac{\sigma_{\text{out}}}{|\mu_{\text{out}}|}\right)
$$

-- the number of decimal digits of $q$ that survive an input perturbation at
the last representable bit. $\mu_{\text{out}}$ and $\sigma_{\text{out}}$ are
the sample mean and standard deviation of $q$ across the $N$ perturbed
refits.

Limitation (recorded honestly, not oversold): this is an *estimate*, not
CADNA's/Shaman's rigorous discrete stochastic arithmetic bound. It measures
sensitivity to one specific, small, randomly-directed perturbation ensemble
rather than proving a worst-case error bound over every IEEE-754 rounding
choice, and the sample standard deviation over only 50 trials is itself
uncertain to roughly $\pm 10\%$ relative (the $\chi^2_{49}$ spread of a
50-sample variance estimate). Treat every digit count below as a first,
honest measurement -- not a certified one.

The case fit is a clean two-Gaussian-plus-linear-background spectrum of the
kind the benchmark actually runs (see
``docs/tutorials/gallery/weighted_fitting.py`` and the recovery cases in
``tests/unit/spectrafit_core/test_fit.py``) -- moderate noise, well-separated
peaks, none of the pathological near-degeneracy of e.g.
``spectrafit_vs_lmfit_complex.py``.

Usage::

    uv run python scripts/measure_significant_digits.py
    uv run python scripts/measure_significant_digits.py --trials 200 --seed 7

Prints a Markdown table (quantity, mu, sigma, significant digits) to stdout.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from spectrafit_core import (
    FitGraph,
    FitResult,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
    fit,
)

DEFAULT_TRIALS = 50
DEFAULT_SEED = 20260821

# Two well-separated Gaussians on a linear background, moderate Gaussian
# noise -- realistic, not pathological. Truth is deliberately different from
# the initial guess so every refit does real solver work each trial.
TRUE_PARAMS = {
    "p0": {"amplitude": 3.0, "center": 1.0, "sigma": 1.2},
    "p1": {"amplitude": 2.0, "center": 6.0, "sigma": 0.9},
    "bg": {"slope": 0.05, "intercept": 0.3},
}
INIT_PARAMS = {
    "p0": {"amplitude": 2.5, "center": 0.8, "sigma": 1.0},
    "p1": {"amplitude": 1.8, "center": 6.2, "sigma": 1.0},
    "bg": {"slope": 0.0, "intercept": 0.0},
}
N_POINTS = 150
X_RANGE = (-5.0, 10.0)
NOISE_SIGMA = 0.05
DATA_SEED = 0  # Fixed independently of --seed: the case itself must not move.


def _synthesize_case() -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Build the fixed noisy two-Gaussian-plus-linear-background dataset."""
    x = np.linspace(*X_RANGE, N_POINTS)
    p0, p1, bg = TRUE_PARAMS["p0"], TRUE_PARAMS["p1"], TRUE_PARAMS["bg"]
    y = (
        p0["amplitude"] * np.exp(-0.5 * ((x - p0["center"]) / p0["sigma"]) ** 2)
        + p1["amplitude"] * np.exp(-0.5 * ((x - p1["center"]) / p1["sigma"]) ** 2)
        + bg["slope"] * x
        + bg["intercept"]
    )
    rng = np.random.default_rng(DATA_SEED)
    return x, y + rng.normal(0.0, NOISE_SIGMA, size=y.shape)


def _build_graph() -> FitGraph:
    """Return a fresh graph at the (fixed, non-truth) initial guess."""
    return FitGraph(
        nodes=[
            ModelNodeSpec(
                id="p0",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=INIT_PARAMS["p0"]["amplitude"]),
                    "center": Parameter(value=INIT_PARAMS["p0"]["center"]),
                    "sigma": Parameter(value=INIT_PARAMS["p0"]["sigma"], min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="p1",
                model_type=ModelType.GAUSSIAN,
                parameters={
                    "amplitude": Parameter(value=INIT_PARAMS["p1"]["amplitude"]),
                    "center": Parameter(value=INIT_PARAMS["p1"]["center"]),
                    "sigma": Parameter(value=INIT_PARAMS["p1"]["sigma"], min=1e-3),
                },
            ),
            ModelNodeSpec(
                id="bg",
                model_type=ModelType.LINEAR,
                parameters={
                    "slope": Parameter(value=INIT_PARAMS["bg"]["slope"]),
                    "intercept": Parameter(value=INIT_PARAMS["bg"]["intercept"]),
                },
            ),
        ],
    )


def _perturb_one_ulp(arr: NDArray[np.float64], rng: np.random.Generator) -> NDArray[np.float64]:
    r"""Perturb every element of `arr` by one ulp in a random direction.

    Each element moves via :func:`numpy.nextafter` toward $+\infty$ or
    $-\infty$, the direction chosen independently per element -- exactly one
    representable float64 step away from its original value, the smallest
    possible non-zero perturbation.
    """
    toward_positive = rng.integers(0, 2, size=arr.shape).astype(bool)
    target = np.where(toward_positive, np.inf, -np.inf)
    return np.nextafter(arr, target)


def significant_digits(values: list[float]) -> float:
    r"""Return $s = -\log_{10}(\sigma_{\text{out}} / |\mu_{\text{out}}|)$.

    The number of decimal digits of a reported quantity that are stable
    across the perturbed-refit ensemble. Returns ``math.inf`` when the
    ensemble is exactly constant (the perturbation had no measurable effect
    at float64 resolution) and ``math.nan`` when ``mu`` is zero or fewer
    than two finite samples were collected (no ratio can be formed).
    """
    arr = np.asarray(values, dtype=np.float64)
    finite = arr[np.isfinite(arr)]
    if finite.size < 2:
        return math.nan
    mu, sd = float(finite.mean()), float(finite.std(ddof=1))
    if mu == 0.0:
        return math.nan
    if sd == 0.0:
        return math.inf
    return -math.log10(sd / abs(mu))


@dataclass
class Ensemble:
    """Collected per-quantity samples across the perturbed-refit ensemble."""

    samples: dict[str, list[float]] = field(default_factory=dict)
    n_success: int = 0
    n_failed: int = 0

    def add(self, name: str, value: float | None) -> None:
        """Record one sample for `name`, skipping ``None`` (unavailable)."""
        if value is None:
            return
        self.samples.setdefault(name, []).append(float(value))


def _collect(result: FitResult, ensemble: Ensemble) -> None:
    """Fold one fit result's reported quantities into `ensemble`."""
    ensemble.add("chi2", result.chi2)
    ensemble.add("reduced_chi2", result.reduced_chi2)
    ensemble.add("r_squared", result.r_squared)
    ensemble.add("aic", result.aic)
    ensemble.add("bic", result.bic)
    ensemble.add("condition_number", result.condition_number)
    for name, param in result.params.items():
        ensemble.add(f"{name}.value", param.value)
        ensemble.add(f"{name}.stderr", param.stderr)


def run(trials: int, seed: int) -> Ensemble:
    """Run the perturb-refit ensemble and return the collected samples."""
    x, y = _synthesize_case()
    rng = np.random.default_rng(seed)
    ensemble = Ensemble()
    for _ in range(trials):
        x_pert = _perturb_one_ulp(x, rng)
        y_pert = _perturb_one_ulp(y, rng)
        data = MeasurementData(x=x_pert.tolist(), y=y_pert.tolist())
        result = fit(_build_graph(), data)
        if not result.success:
            ensemble.n_failed += 1
            continue
        ensemble.n_success += 1
        _collect(result, ensemble)
    return ensemble


def _format_digits(s: float) -> str:
    """Render a significant-digit figure for the table (handles inf/nan)."""
    if math.isnan(s):
        return "n/a"
    if math.isinf(s):
        return ">15.9 (float64 noise floor)"
    return f"{s:.2f}"


def render_table(ensemble: Ensemble) -> str:
    """Render the quantity -> significant-digits table as Markdown."""
    lines = [
        "| quantity | n | mu | sigma | significant digits |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in sorted(ensemble.samples):
        values = ensemble.samples[name]
        arr = np.asarray(values, dtype=np.float64)
        mu = float(arr.mean())
        sd = float(arr.std(ddof=1)) if arr.size > 1 else math.nan
        digits = significant_digits(values)
        lines.append(
            f"| `{name}` | {len(values)} | {mu:.6g} | {sd:.3g} | {_format_digits(digits)} |",
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Entry point: run the ensemble and print the Markdown table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args(argv)

    ensemble = run(args.trials, args.seed)
    total = ensemble.n_success + ensemble.n_failed
    print(f"# converged {ensemble.n_success}/{total} trials\n")
    print(render_table(ensemble))
    return 0


if __name__ == "__main__":
    sys.exit(main())
