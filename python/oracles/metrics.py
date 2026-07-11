"""Statistics that turn fit outcomes into the frozen report contract sub-objects.

Everything here is computed from real measurements (timing repetitions, Monte-Carlo
noise realizations, covariance at the solution); nothing is fabricated. The 1/√n
stability projections are derived from the measured spread, not invented.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from typing import NamedTuple

import numpy as np

from oracles.bench_contract import (
    AccuracyDist,
    Point2D,
    SpreadPt,
    TimingDist,
    Uncertainty,
)
from oracles.models import Array

# Canonical quantile vectors for the timing / accuracy distributions.
# Both are pinned by the frozen `BenchReport` contract: `TimingDist` exposes
# {median, p5, p25, p75, p95} and `AccuracyDist` exposes {median, p5, p25, p75}.
# Note: the 0.5 slot below feeds the `median` field, not a (non-existent)
# `p50` field — neither contract model declares `p50`. Keeping the quantiles
# named (instead of inline literals) makes the contract↔implementation link
# explicit and prevents an accidental tuple drift between the two helpers.
# Unpack order in the call sites: `p5, p25, med, p75[, p95]`.
_TIMING_QUANTILES: tuple[float, ...] = (0.05, 0.25, 0.5, 0.75, 0.95)
_ACCURACY_QUANTILES: tuple[float, ...] = (0.05, 0.25, 0.5, 0.75)

# Numerical floor for covariance-matrix diagonal entries before the √ that
# normalises off-diagonals into a correlation matrix. Anything smaller than
# this would produce NaN/inf in the division; the value matches the historical
# inline literal so the pre-refactor JSON output is preserved byte-for-byte.
_CORR_DIAG_FLOOR: float = 1e-30


def pcts(xs: list[float], qs: tuple[float, ...]) -> list[float]:
    """Linear-interpolated percentiles (q in [0,1]) of *xs*."""
    s = sorted(xs)
    out = []
    for q in qs:
        if len(s) == 1:
            out.append(s[0])
            continue
        i = q * (len(s) - 1)
        lo = int(math.floor(i))
        hi = min(lo + 1, len(s) - 1)
        out.append(s[lo] + (s[hi] - s[lo]) * (i - lo))
    return out


def timing_dist(ms: list[float]) -> TimingDist:
    """Build a :class:`TimingDist` from raw per-rep milliseconds."""
    p5, p25, med, p75, p95 = pcts(ms, _TIMING_QUANTILES)
    mean = sum(ms) / len(ms)
    var = sum((v - mean) ** 2 for v in ms) / len(ms)
    cv = 100.0 * math.sqrt(var) / mean if mean > 0 else 0.0
    return TimingDist(
        raw=list(ms),
        median=med,
        mean=mean,
        p5=p5,
        p25=p25,
        p75=p75,
        p95=p95,
        iqr=p75 - p25,
        cv=cv,
    )


def accuracy_dist(red_chi2_samples: list[float]) -> AccuracyDist:
    """Build an :class:`AccuracyDist` from reduced-χ² Monte-Carlo samples."""
    p5, p25, med, p75 = pcts(red_chi2_samples, _ACCURACY_QUANTILES)
    return AccuracyDist(raw=list(red_chi2_samples), median=med, p5=p5, p25=p25, p75=p75)


def ecdf(values: list[float]) -> list[Point2D]:
    """Empirical CDF of *values* as (x, y) points (y in [0,1]); empty → []."""
    s = sorted(values)
    n = len(s)
    if n == 0:
        return []
    return [Point2D(x=float(v), y=(i + 1) / n) for i, v in enumerate(s)]


def cov_to_corr(cov: list[list[float | None]] | None) -> list[list[float]]:
    """Convert a covariance matrix to a correlation matrix (zeros if unavailable)."""
    if not cov:
        return []
    mat = np.array(
        [[0.0 if v is None else float(v) for v in row] for row in cov], dtype=float
    )
    diag_sd = np.sqrt(np.clip(np.diag(mat), _CORR_DIAG_FLOOR, None))
    corr = mat / np.outer(diag_sd, diag_sd)
    corr = np.clip(np.nan_to_num(corr, nan=0.0), -1.0, 1.0)
    return corr.tolist()


def spread_vs_runs(samples: list[float], runs_sched: list[int]) -> list[SpreadPt]:
    """Mean ± sd of *samples* subsampled to each run count (real 1/√n behaviour).

    The sample sd needs ≥2 points; for a single-point subsample sd is 0.0 (never
    ``nan`` from ``ddof=1`` dividing by zero).
    """
    out = []
    arr = np.array(samples, dtype=float)
    for n in runs_sched:
        sub = arr[: max(1, min(n, len(arr)))]
        mean = float(np.mean(sub)) if sub.size else 0.0
        sd = float(np.std(sub, ddof=1)) if sub.size >= 2 else 0.0
        out.append(SpreadPt(n=n, mean=mean, sd=sd))
    return out


def amortization_curve(
    cold_ms: float, hot_ms: float, schedule: list[int]
) -> list[Point2D]:
    """Per-run time as the one-off cold cost amortizes over cumulative runs."""
    return [Point2D(x=k, y=(cold_ms + hot_ms * (k - 1)) / k) for k in schedule]


class _PullSample(NamedTuple):
    """One valid MC sample: parameter name, its σ, and the resulting pull value.

    Named fields replace positional unpacking at every call site — readers see
    ``s.sigma`` / ``s.pull`` instead of counting tuple positions. The class is
    private (leading underscore): it is an internal helper of
    :func:`pulls_from_mc`, not part of the report contract.
    """

    key: str
    sigma: float
    pull: float


def _iter_valid_pulls(
    estimates: list[dict[str, float]],
    stderrs: list[dict[str, float | None]],
    true_params: dict[str, float],
) -> Iterator[_PullSample]:
    """Yield a :class:`_PullSample` for every valid (est, se) × true_params sample.

    A sample is valid when σ is a positive number AND the estimate dict carries the
    parameter key. Invalid samples (None / non-positive σ / missing key) are skipped
    silently — they contribute neither to pulls nor to the σ vector.
    """
    for est, se in zip(estimates, stderrs):
        for key, true in true_params.items():
            sigma = se.get(key)
            if sigma is None or sigma <= 0 or key not in est:
                continue
            yield _PullSample(key=key, sigma=sigma, pull=(est[key] - true) / sigma)


def pulls_from_mc(
    estimates: list[dict[str, float]],
    stderrs: list[dict[str, float | None]],
    true_params: dict[str, float],
) -> Uncertainty:
    """Pull = (estimate − truth)/σ across MC fits; coverage = frac |pull|<1.

    Skips MC samples where σ is ``None``, ≤ 0, or the estimate key is absent
    (see :func:`_iter_valid_pulls` for the skip rules).

    The returned ``sigma`` vector is the **last-seen** σ per parameter — each MC
    iteration that contributes a sample overwrites the previous σ for that key,
    so the final entry is whichever sample happened to be processed last (output
    is then sorted alphabetically by key). This is a diagnostic field, not a
    statistical summary; consumers wanting mean/median σ should reduce across MC
    repetitions themselves. The "last" choice is preserved verbatim from the
    pre-refactor implementation so existing report-payload tests pin the same
    value; revisiting whether this should instead be ``mean(sigma)`` or
    ``median(sigma)`` is tracked as a separate Plan C3 concern and is
    intentionally out of scope here.
    """
    samples = list(_iter_valid_pulls(estimates, stderrs, true_params))
    pulls = [s.pull for s in samples]
    last_sigma = {s.key: s.sigma for s in samples}
    # coverage is None when no valid σ was available (empty pulls means every σ
    # was None / non-positive). A genuine "0% within 1σ" failure requires at
    # least one valid pull that happened to be |p| ≥ 1; that produces 0.0, not
    # None.  The distinction is EF-PY-06: downstream consumers (audit W2b,
    # web renders) must treat None as "σ not reported" rather than "0% coverage".
    coverage: float | None = (
        sum(1 for p in pulls if abs(p) < 1.0) / len(pulls) if pulls else None
    )
    return Uncertainty(
        pulls=pulls or [0.0],
        coverage=coverage,
        sigma=[last_sigma[k] for k in sorted(last_sigma)] or [0.0],
    )


def r2_of(y: Array, fit: Array) -> float:
    """Coefficient of determination."""
    ss_res = float(np.sum((y - fit) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 1.0


def rmse_of(y: Array, fit: Array) -> float:
    """Root-mean-square error. Canonical recomputation oracle for wire W2a."""
    diff = np.asarray(y) - np.asarray(fit)
    return float(np.sqrt(np.mean(diff * diff)))


def chi2_red_of(y: Array, fit: Array, sigma: Array | None, dof: int) -> float:
    """Reduced χ². If ``sigma`` is None, falls back to σ=1 (unweighted)."""
    y_arr = np.asarray(y)
    fit_arr = np.asarray(fit)
    if sigma is None:
        weights = np.ones_like(y_arr)
    else:
        weights = 1.0 / np.asarray(sigma) ** 2
    residual = (y_arr - fit_arr) ** 2 * weights
    return float(residual.sum() / max(dof, 1))
