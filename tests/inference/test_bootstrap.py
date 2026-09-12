import numpy as np
from oracles.inference import bootstrap_ci


def test_bootstrap_ci_brackets_the_mean_of_normal_data():
    rng = np.random.default_rng(0)
    samples = list(rng.normal(10.0, 1.0, size=500))
    lo, hi = bootstrap_ci(samples, stat=np.mean, b=2000, alpha=0.05, seed=42)
    assert lo < 10.0 < hi
    assert hi - lo < 0.5  # ~ 2*1.96*sd/sqrt(n)


def test_bootstrap_ci_is_deterministic_under_fixed_seed():
    samples = [1.0, 2.0, 3.0, 4.0, 5.0]
    a = bootstrap_ci(samples, stat=np.mean, b=1000, alpha=0.05, seed=7)
    b = bootstrap_ci(samples, stat=np.mean, b=1000, alpha=0.05, seed=7)
    assert a == b


def test_bootstrap_ci_single_sample_returns_point():
    lo, hi = bootstrap_ci([3.0], stat=np.mean, b=100, alpha=0.05, seed=1)
    assert lo == hi == 3.0
