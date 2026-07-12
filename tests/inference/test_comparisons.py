from oracles.inference import speedup_ci, delta_r2_ci

def test_speedup_ci_brackets_the_point_ratio():
    base = [10.0, 11.0, 9.0, 10.5, 9.5]   # baseline ms reps
    subj = [1.0, 1.1, 0.9, 1.05, 0.95]    # subject ms reps (~10x faster)
    lo, point, hi = speedup_ci(base, subj, b=2000, alpha=0.05, seed=3)
    assert lo < point < hi
    assert 8.0 < point < 12.0

def test_delta_r2_ci_centered_near_zero_for_equal_fits():
    a = [0.9991, 0.9992, 0.9990, 0.9993]
    b = [0.9990, 0.9991, 0.9992, 0.9991]
    lo, point, hi = delta_r2_ci(a, b, b_resamples=2000, alpha=0.05, seed=5)
    assert lo < 0.0 < hi  # indistinguishable → CI straddles 0
