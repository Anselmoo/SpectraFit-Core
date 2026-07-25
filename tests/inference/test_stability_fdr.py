from oracles.inference import winner_stability, bh_correct


def test_winner_stability_high_when_one_backend_dominates():
    # per-case score vectors keyed by backend; "a" always best
    scores = {"a": [10, 11, 9, 10], "b": [1, 1, 2, 1], "c": [3, 2, 3, 2]}
    res = winner_stability(scores, b=2000, seed=1)
    assert res["a"] > 0.95
    assert res["b"] < 0.05


def test_winner_stability_low_when_tie():
    # Alternating wins: a wins 2 cases, b wins 2 cases — no dominant backend
    scores = {"a": [10, 1, 10, 1], "b": [1, 10, 1, 10]}
    res = winner_stability(scores, b=2000, seed=1)
    assert abs(res["a"] - 0.5) < 0.25  # no robust winner, some resampling variance


def test_bh_correct_flags_only_significant():
    pvals = [0.001, 0.04, 0.20, 0.50]
    rejected, q = bh_correct(pvals, q=0.05)
    assert rejected[0] is True
    assert rejected[3] is False
    assert len(q) == 4
