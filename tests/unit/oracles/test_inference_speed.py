"""Test suite for geomean_speedup_test inferential statistic."""

from oracles.inference import geomean_speedup_test


def test_clearly_faster_passes():
    sp = [2.0, 3.0, 2.5, 4.0, 2.2, 3.1, 2.8, 3.3]  # all > 1×
    s = geomean_speedup_test(sp, b=1000, seed=1)
    assert s.skipped is False
    assert s.passed is True
    assert s.ci_lo > 1.0 and s.excludes_one is True
    assert s.sign_p < 0.05  # significant majority of wins


def test_tie_does_not_pass():
    sp = [1.05, 0.95, 1.0, 0.9, 1.1, 0.98, 1.02, 1.0]  # straddles 1×
    s = geomean_speedup_test(sp, b=1000, seed=1)
    assert s.passed is False
    assert s.ci_lo <= 1.0 and s.excludes_one is False


def test_too_few_skipped():
    s = geomean_speedup_test([2.0])
    assert s.skipped is True and s.passed is False
