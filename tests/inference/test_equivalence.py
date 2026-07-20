from oracles.inference import tost_equivalence


def test_tost_declares_equivalence_when_within_margin():
    a = [0.9991, 0.9992, 0.9990, 0.9993, 0.9991]
    b = [0.9990, 0.9991, 0.9992, 0.9991, 0.9990]
    res = tost_equivalence(a, b, margin=1e-3, alpha=0.05)
    assert res.equivalent is True
    assert res.margin == 1e-3


def test_tost_rejects_equivalence_when_truly_different():
    a = [0.99, 0.99, 0.99, 0.99]
    b = [0.50, 0.51, 0.49, 0.50]
    res = tost_equivalence(a, b, margin=1e-3, alpha=0.05)
    assert res.equivalent is False
