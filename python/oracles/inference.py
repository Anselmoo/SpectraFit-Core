"""Inferential statistics for the trustworthy benchmark.

Pure functions over plain sequences — no engine coupling. Every comparison the
report makes carries an interval, an equivalence verdict, or a stability score,
so the numbers state their own uncertainty rather than asserting it.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

import numpy as np
from pydantic import BaseModel, ConfigDict

CI = tuple[float, float]


def bootstrap_ci(
    samples: Sequence[float],
    *,
    stat: Callable[[np.ndarray], float],
    b: int,
    alpha: float,
    seed: int,
) -> CI:
    """Percentile-bootstrap (1-alpha) CI of ``stat`` over ``samples``.

    Single-sample input returns a degenerate point interval (lo == hi); a
    bootstrap over one value has no spread and must not raise.
    """
    arr = np.asarray(samples, dtype=float)
    if arr.size <= 1:
        v = float(arr[0]) if arr.size else 0.0
        return (v, v)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, arr.size, size=(b, arr.size))
    stats = np.array([stat(arr[row]) for row in idx])
    lo = float(np.quantile(stats, alpha / 2))
    hi = float(np.quantile(stats, 1 - alpha / 2))
    return (lo, hi)


def speedup_ci(
    baseline_ms: Sequence[float],
    subject_ms: Sequence[float],
    *,
    b: int,
    alpha: float,
    seed: int,
) -> tuple[float, float, float]:
    """(lo, point, hi) CI for speedup = median(baseline)/median(subject).

    Resamples each leg independently (the reps are unpaired across backends)
    and bootstraps the ratio of medians.
    """
    base = np.asarray(baseline_ms, dtype=float)
    subj = np.asarray(subject_ms, dtype=float)
    point = float(np.median(base) / np.median(subj))
    if base.size <= 1 or subj.size <= 1:
        return (point, point, point)
    rng = np.random.default_rng(seed)
    bi = rng.integers(0, base.size, size=(b, base.size))
    si = rng.integers(0, subj.size, size=(b, subj.size))
    ratios = np.median(base[bi], axis=1) / np.median(subj[si], axis=1)
    return (
        float(np.quantile(ratios, alpha / 2)),
        point,
        float(np.quantile(ratios, 1 - alpha / 2)),
    )


def delta_r2_ci(
    r2_a: Sequence[float],
    r2_b: Sequence[float],
    *,
    b_resamples: int,
    alpha: float,
    seed: int,
) -> tuple[float, float, float]:
    """(lo, point, hi) CI for mean(r2_a) - mean(r2_b)."""
    a = np.asarray(r2_a, dtype=float)
    b = np.asarray(r2_b, dtype=float)
    point = float(np.mean(a) - np.mean(b))
    if a.size <= 1 or b.size <= 1:
        return (point, point, point)
    rng = np.random.default_rng(seed)
    ai = rng.integers(0, a.size, size=(b_resamples, a.size))
    bi = rng.integers(0, b.size, size=(b_resamples, b.size))
    diffs = np.mean(a[ai], axis=1) - np.mean(b[bi], axis=1)
    return (
        float(np.quantile(diffs, alpha / 2)),
        point,
        float(np.quantile(diffs, 1 - alpha / 2)),
    )


class EquivalenceVerdict(BaseModel):
    """Result of a two-one-sided-tests (TOST) equivalence test."""

    model_config = ConfigDict(extra="forbid")
    equivalent: bool
    margin: float
    diff: float
    p_lower: float
    p_upper: float


def tost_equivalence(
    a: Sequence[float], b: Sequence[float], *, margin: float, alpha: float
) -> EquivalenceVerdict:
    """TOST: are mean(a), mean(b) equivalent within +/- margin?

    Two one-sided Welch t-tests; equivalent iff BOTH reject at alpha (the
    diff's (1-2*alpha) CI lies inside [-margin, +margin]). 'Saturated' is then
    a positive equivalence claim, not an unthresholded r2>0.999.
    """
    from scipy import stats as st

    x = np.asarray(a, dtype=float)
    y = np.asarray(b, dtype=float)
    diff = float(np.mean(x) - np.mean(y))
    se = float(np.sqrt(np.var(x, ddof=1) / x.size + np.var(y, ddof=1) / y.size))
    if se == 0.0:
        equiv = abs(diff) < margin
        return EquivalenceVerdict(
            equivalent=equiv,
            margin=margin,
            diff=diff,
            p_lower=0.0 if equiv else 1.0,
            p_upper=0.0 if equiv else 1.0,
        )
    dof = x.size + y.size - 2
    t_lower = (diff - (-margin)) / se
    t_upper = (diff - margin) / se
    p_lower = float(1 - st.t.cdf(t_lower, dof))  # H0: diff <= -margin
    p_upper = float(st.t.cdf(t_upper, dof))  # H0: diff >= +margin
    equivalent = (p_lower < alpha) and (p_upper < alpha)
    return EquivalenceVerdict(
        equivalent=equivalent,
        margin=margin,
        diff=diff,
        p_lower=p_lower,
        p_upper=p_upper,
    )


def tost_paired(
    deltas: Sequence[float], *, margin: float, alpha: float
) -> EquivalenceVerdict:
    """One-sample TOST on PAIRED differences: is mean(deltas) within ±margin?

    Use for paired comparisons — e.g. per-case Δr² between two backends measured
    on the *same* case. An unpaired two-sample test would wrongly inflate the
    standard error with case-to-case spread and mask a real equivalence; the
    paired test's variance is the spread of the per-case differences, which is
    tiny when the backends agree case-by-case. Equivalent iff the (1−2α) CI of
    mean(deltas) lies inside [−margin, +margin].
    """
    from scipy import stats as st

    d = np.asarray(deltas, dtype=float)
    n = d.size
    diff = float(np.mean(d)) if n else 0.0
    sd = float(np.std(d, ddof=1)) if n >= 2 else 0.0
    se = sd / float(np.sqrt(n)) if (n >= 1 and sd > 0) else 0.0
    if se == 0.0:
        equiv = abs(diff) < margin
        return EquivalenceVerdict(
            equivalent=equiv,
            margin=margin,
            diff=diff,
            p_lower=0.0 if equiv else 1.0,
            p_upper=0.0 if equiv else 1.0,
        )
    dof = n - 1
    p_lower = float(1 - st.t.cdf((diff - (-margin)) / se, dof))  # H0: diff <= -margin
    p_upper = float(st.t.cdf((diff - margin) / se, dof))  # H0: diff >= +margin
    equivalent = (p_lower < alpha) and (p_upper < alpha)
    return EquivalenceVerdict(
        equivalent=equivalent,
        margin=margin,
        diff=diff,
        p_lower=p_lower,
        p_upper=p_upper,
    )


def winner_stability(
    scores: Mapping[str, Sequence[float]], *, b: int, seed: int
) -> dict[str, float]:
    """Fraction of bootstrap resamples in which each backend is the winner.

    Resamples the per-case score vectors (paired across backends by case index)
    and records the argmax-mean each round. A low max stability ⇒ no robust
    winner — which the report must say plainly rather than crowning noise.
    """
    keys = list(scores)
    mat = np.array([scores[k] for k in keys], dtype=float)  # (n_backends, n_cases)
    n_cases = mat.shape[1]
    rng = np.random.default_rng(seed)
    wins = {k: 0 for k in keys}
    for _ in range(b):
        idx = rng.integers(0, n_cases, size=n_cases)
        means = mat[:, idx].mean(axis=1)
        wins[keys[int(np.argmax(means))]] += 1
    return {k: wins[k] / b for k in keys}


def bh_correct(pvalues: Sequence[float], *, q: float) -> tuple[list[bool], list[float]]:
    """Benjamini-Hochberg FDR. Returns (rejected mask, BH-adjusted q-values)."""
    p = np.asarray(pvalues, dtype=float)
    n = p.size
    order = np.argsort(p)
    ranked = p[order]
    adj = ranked * n / (np.arange(n) + 1)
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    adj = np.clip(adj, 0.0, 1.0)
    out_q = np.empty(n)
    out_q[order] = adj
    return [bool(v <= q) for v in out_q], [float(v) for v in out_q]


class CalibrationStat(BaseModel):
    """Result of a binomial calibration test on parameter pulls."""

    model_config = ConfigDict(extra="forbid")
    n: int
    coverage: float
    coverage_ci_lo: float
    coverage_ci_hi: float
    nominal: float
    binomial_p: float
    ks_stat: float
    ks_p: float
    alpha: float
    equivalence_margin: float
    passed: bool
    skipped: bool


def coverage_test(
    pulls: Sequence[float],
    *,
    nominal: float = 0.6827,
    alpha: float = 0.025,
    min_pulls: int = 20,
    equivalence_margin: float = 0.03,
) -> CalibrationStat:
    """Test if parameter pulls indicate well-calibrated uncertainties.

    A parameter pull is (θ_est - θ_true) / σ_est. In well-calibrated fits,
    pulls ~ N(0, 1), so ~68.27% should fall within [-1, 1].

    The gating verdict (``passed``) uses a practical-equivalence rule: the
    Clopper–Pearson CI of the empirical coverage must lie entirely within
    ``[nominal − equivalence_margin, nominal + equivalence_margin]``.  This is
    the standard CI-inclusion TOST for a one-sample proportion — it avoids the
    classic statistical-vs-practical-significance trap at large n where a
    point-null binomial test rejects a negligible (< 2 pp) deviation.

    The strict point-null ``binomial_p`` is always computed and retained as an
    honest diagnostic (it appears in ``CalibrationStat.binomial_p`` and in the
    audit wire evidence string) so the dashboard can still report "coverage
    0.668 vs nominal 0.6827, strict p < 0.001" — only the binary gate changes.

    Args:
        pulls: Sequence of parameter pulls.
        nominal: Target coverage (default 68.27%, the 1-σ interval).
        alpha: Significance level for the Clopper-Pearson CI (default 0.025,
               giving a 97.5% CI used for the equivalence inclusion test).
        min_pulls: Minimum pulls to avoid skipping (default 20).
        equivalence_margin: Half-width of the pre-registered equivalence band
               around ``nominal`` (default 0.03 = ±3 pp).  ``passed`` is
               ``True`` iff ``coverage_ci_lo >= nominal - margin`` AND
               ``coverage_ci_hi <= nominal + margin``.

    Returns:
        CalibrationStat with coverage point estimate, Clopper-Pearson CI,
        binomial p-value (honest strict diagnostic), KS test vs N(0,1),
        equivalence_margin, and pass/skip verdict.
        If n < min_pulls, skipped=True and passed=False (insufficient data).
    """
    from scipy import stats

    # Filter out non-finite values
    finite = [p for p in pulls if p == p and abs(p) != float("inf")]
    n = len(finite)

    # Insufficient data → skip
    if n < min_pulls:
        return CalibrationStat(
            n=n,
            coverage=0.0,
            coverage_ci_lo=0.0,
            coverage_ci_hi=0.0,
            nominal=nominal,
            binomial_p=1.0,
            ks_stat=0.0,
            ks_p=1.0,
            alpha=alpha,
            equivalence_margin=equivalence_margin,
            passed=False,
            skipped=True,
        )

    # Coverage: fraction of pulls within [-1, 1]
    k = sum(1 for p in finite if abs(p) < 1.0)
    coverage = k / n

    # Binomial test: exact two-sided, Clopper-Pearson CI
    # binomial_p is retained as the HONEST STRICT DIAGNOSTIC (point-null H0:
    # coverage = nominal).  At large n this has so much power it rejects
    # practically negligible deviations — we keep it for reporting but do NOT
    # use it for the gate verdict.
    bt = stats.binomtest(k, n, nominal)
    ci = bt.proportion_ci(confidence_level=1 - alpha, method="exact")

    # Kolmogorov-Smirnov test: pulls vs N(0, 1)
    ks = stats.kstest(finite, "norm")

    # Gate verdict: CI-inclusion TOST for a one-sample proportion.
    # passed iff the (1-alpha) Clopper-Pearson CI lies entirely within
    # [nominal - margin, nominal + margin].  This is the standard equivalence
    # test for a proportion: both endpoints of the CI must fall inside the band.
    lo = float(ci.low)
    hi = float(ci.high)
    passed = bool(
        lo >= nominal - equivalence_margin and hi <= nominal + equivalence_margin
    )

    return CalibrationStat(
        n=n,
        coverage=coverage,
        coverage_ci_lo=lo,
        coverage_ci_hi=hi,
        nominal=nominal,
        binomial_p=float(bt.pvalue),
        ks_stat=float(ks.statistic),
        ks_p=float(ks.pvalue),
        alpha=alpha,
        equivalence_margin=equivalence_margin,
        passed=passed,
        skipped=False,
    )


class SpeedStat(BaseModel):
    """Result of a geomean speedup significance test."""

    model_config = ConfigDict(extra="forbid")
    geomean_speedup: float
    ci_lo: float
    ci_hi: float
    excludes_one: bool
    sign_p: float
    wilcoxon_p: float
    alpha: float
    passed: bool
    skipped: bool


def geomean_speedup_test(
    per_case_speedups: Sequence[float],
    *,
    b: int = 2000,
    seed: int = 20260612,
    alpha: float = 0.025,
) -> SpeedStat:
    """Test if subject is significantly faster than baseline using geomean speedup.

    The test computes a bootstrap CI for the geometric mean speedup over cases,
    then validates against 1× with a sign test and Wilcoxon signed-rank test.
    Pass criterion: CI lower bound > 1.0 (excludes_one=True).

    Args:
        per_case_speedups: Sequence of speedup ratios (baseline_ms / subject_ms),
                          one per case. NaN and non-positive values are filtered.
        b: Bootstrap resamples (default 2000).
        seed: Random seed for reproducibility (default 20260612).
        alpha: Significance level for CI (default 0.025).

    Returns:
        SpeedStat with geomean, CI, exclusion verdict, p-values, and pass/skip.
        Empty or <2 valid inputs → skipped=True, passed=False.
    """
    from scipy import stats

    # Filter out NaN and non-positive speedups
    sp = [s for s in per_case_speedups if s == s and s > 0]
    m = len(sp)

    # Insufficient data → skip
    if m < 2:
        return SpeedStat(
            geomean_speedup=0.0,
            ci_lo=0.0,
            ci_hi=0.0,
            excludes_one=False,
            sign_p=1.0,
            wilcoxon_p=1.0,
            alpha=alpha,
            passed=False,
            skipped=True,
        )

    # Convert to log-speedups (log-scale is additive for ratios)
    logs = np.log(np.asarray(sp))
    geo = float(np.exp(logs.mean()))

    # Bootstrap CI on geomean
    rng = np.random.default_rng(seed)
    boots = np.exp([rng.choice(logs, size=m, replace=True).mean() for _ in range(b)])
    lo, hi = (float(x) for x in np.quantile(boots, [alpha, 1 - alpha]))

    # Sign test: fraction of wins (speedup > 1×)
    wins = sum(1 for s in sp if s > 1.0)
    sign_p = float(stats.binomtest(wins, m, 0.5, alternative="greater").pvalue)

    # Wilcoxon signed-rank test: log-speedups vs 0 (median log-speedup > 0)
    try:
        wilcoxon_p = float(stats.wilcoxon(logs, alternative="greater").pvalue)
    except ValueError:  # all-zero differences
        wilcoxon_p = 1.0

    excludes_one = bool(lo > 1.0)
    passed = excludes_one

    return SpeedStat(
        geomean_speedup=geo,
        ci_lo=lo,
        ci_hi=hi,
        excludes_one=excludes_one,
        sign_p=sign_p,
        wilcoxon_p=wilcoxon_p,
        alpha=alpha,
        passed=passed,
        skipped=False,
    )
