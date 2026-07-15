"""Paired TOST: the saturation claim is a per-case comparison, not a mean-of-means.

Regression test for the run_025 finding where the unpaired test reported
`easy equivalent=False` despite a mean Δr² of ~1e-15 — the case-to-case r²
spread inflated the unpaired standard error and masked a real equivalence.
"""

from oracles.inference import tost_paired, tost_equivalence


def test_paired_finds_equivalence_when_unpaired_fails_due_to_case_spread():
    # r² varies a lot case-to-case (0.90..0.9999) but the two backends AGREE
    # per case (Δ ~ 1e-6). Paired TOST → equivalent; unpaired is fooled.
    base = [0.90, 0.95, 0.99, 0.999, 0.9999]
    subj = [0.900001, 0.950001, 0.990001, 0.999001, 0.999901]
    deltas = [s - b for s, b in zip(subj, base)]
    assert tost_paired(deltas, margin=1e-3, alpha=0.05).equivalent is True
    # the unpaired two-sample test wrongly rejects equivalence:
    assert tost_equivalence(subj, base, margin=1e-3, alpha=0.05).equivalent is False


def test_paired_rejects_a_consistent_real_difference():
    deltas = [0.01, 0.011, 0.009, 0.0105, 0.0095]  # consistently ~0.01 > margin
    assert tost_paired(deltas, margin=1e-3, alpha=0.05).equivalent is False


def test_paired_identical_is_equivalent():
    assert tost_paired([0.0, 0.0, 0.0], margin=1e-3, alpha=0.05).equivalent is True
