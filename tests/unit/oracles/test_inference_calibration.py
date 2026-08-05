import numpy as np
from oracles.inference import coverage_test


def test_well_calibrated_pulls_pass():
    # n=5000 gives a tight enough Clopper-Pearson CI that the equivalence band
    # [nominal-0.03, nominal+0.03] is reliably satisfied for true N(0,1) pulls.
    # At n=500 the CI half-width (~±0.04) exceeds the ±0.03 margin, so the old
    # n=500 fixture was marginal — upgrade to n=5000 (still fast, <50 ms).
    rng = np.random.default_rng(0)
    pulls = list(rng.standard_normal(5000))
    s = coverage_test(pulls)
    assert s.skipped is False
    assert s.passed is True  # CI within ±0.03 of nominal
    assert abs(s.coverage - 0.6827) < 0.05
    assert s.ks_p > 0.01  # shape consistent with N(0,1)


def test_inflated_sigma_overcovers_and_fails():
    # σ reported 1.6× too large → pulls ~ N(0, 1/1.6) → coverage ≫ 0.68 → reject
    rng = np.random.default_rng(1)
    pulls = list(rng.standard_normal(500) / 1.6)
    s = coverage_test(pulls)
    assert s.passed is False
    assert s.coverage > 0.6827
    assert s.binomial_p < 0.025


def test_deflated_sigma_undercovers_and_fails():
    rng = np.random.default_rng(2)
    pulls = list(rng.standard_normal(500) * 1.6)  # σ too small → pulls too wide
    s = coverage_test(pulls)
    assert s.passed is False
    assert s.coverage < 0.6827


def test_too_few_pulls_skipped():
    s = coverage_test([0.1, -0.2, 0.3], min_pulls=20)
    assert s.skipped is True
    assert s.passed is False


# ---------------------------------------------------------------------------
# A2 fix: practical-equivalence gate (CI-in-band rule)
# ---------------------------------------------------------------------------


def _make_pulls_with_coverage(n: int, coverage: float) -> list[float]:
    """Return n deterministic pulls whose within-1σ fraction equals coverage.

    |pull| < 1.0 counts as "inside"; 0.5 (inside) and 1.5 (outside) are used
    as fixed representatives so there is no RNG variance.
    """
    k = round(coverage * n)
    return [0.5] * k + [1.5] * (n - k)


def test_a2_practically_equivalent_large_n_passes():
    """A2 fix: coverage 0.668 at n=7074 passes with margin=0.03.

    The strict binomial p is well below α (large-n power trap), so the old gate
    would have rejected this as fail.  Under the CI-in-band rule the coverage is
    within ±0.03 of nominal, so passed=True.

    Also verifies that the strict diagnostic (binomial_p) is still reported and
    correctly small — the honest diagnostic is retained, only the gate changes.
    """
    n = 7074
    coverage_target = 0.668  # 1.5 pp below nominal 0.6827
    pulls = _make_pulls_with_coverage(n, coverage_target)
    s = coverage_test(pulls, equivalence_margin=0.03)

    # Gate verdict: CI within [0.6527, 0.7127] → should pass
    assert s.passed is True, (
        f"expected passed=True for coverage≈{s.coverage:.4f} within margin=0.03; "
        f"ci=[{s.coverage_ci_lo:.4f}, {s.coverage_ci_hi:.4f}]"
    )
    # Honest strict diagnostic is retained
    assert s.binomial_p < 0.025, (
        f"binomial_p={s.binomial_p:.4g} should be small (strict diagnostic retained)"
    )
    # New contract field present
    assert s.equivalence_margin == 0.03


def test_a2_genuinely_miscalibrated_fails():
    """A2 fix: coverage 0.55 at large n fails — CI lies outside the ±0.03 band.

    The CI lower bound for coverage≈0.55 at n=7074 is far below nominal−0.03=0.6527,
    so passed=False correctly.
    """
    n = 7074
    pulls = _make_pulls_with_coverage(n, 0.55)
    s = coverage_test(pulls, equivalence_margin=0.03)

    assert s.passed is False, (
        f"expected passed=False for coverage≈{s.coverage:.4f}; "
        f"ci=[{s.coverage_ci_lo:.4f}, {s.coverage_ci_hi:.4f}]"
    )
