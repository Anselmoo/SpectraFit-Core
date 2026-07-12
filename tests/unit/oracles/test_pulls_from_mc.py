"""Unit tests for :func:`oracles.metrics.pulls_from_mc` and ``_iter_valid_pulls``.

The function maps a list of MC fit estimates + stderrs + truth into an
:class:`Uncertainty` object: pulls list, coverage (fraction within 1σ), and the
last-seen σ vector keyed alphabetically. These tests pin the public contract
(signature + return semantics) and the skip rules of the private helper.
"""

from __future__ import annotations

import math

import pytest

from oracles.bench_contract import Uncertainty
from oracles.metrics import _iter_valid_pulls, pulls_from_mc


def test_happy_path_pulls_and_coverage() -> None:
    """3 MC estimates × 2 true params, all valid → pulls + coverage correct."""
    true_params = {"a": 1.0, "b": 2.0}
    estimates = [
        {"a": 1.5, "b": 2.0},  # pull_a = 1.0, pull_b = 0.0
        {"a": 1.0, "b": 2.5},  # pull_a = 0.0, pull_b = 1.0
        {"a": 2.0, "b": 1.0},  # pull_a = 2.0, pull_b = -2.0
    ]
    stderrs: list[dict[str, float | None]] = [
        {"a": 0.5, "b": 0.5},
        {"a": 0.5, "b": 0.5},
        {"a": 0.5, "b": 0.5},
    ]

    out = pulls_from_mc(estimates, stderrs, true_params)

    assert isinstance(out, Uncertainty)
    assert out.pulls == [1.0, 0.0, 0.0, 1.0, 2.0, -2.0]
    # |pull| < 1.0 strict: 0.0, 0.0 → 2/6
    assert out.coverage == pytest.approx(2.0 / 6.0)
    # last_sigma keyed alphabetically; last seen σ for each key = 0.5
    assert out.sigma == [0.5, 0.5]


def test_skips_none_sigma() -> None:
    """A stderr entry of ``None`` is skipped (no pull, no σ contribution)."""
    true_params = {"a": 1.0}
    estimates = [{"a": 1.5}, {"a": 2.0}]
    stderrs: list[dict[str, float | None]] = [
        {"a": None},  # skipped
        {"a": 0.5},  # pull = (2.0 - 1.0) / 0.5 = 2.0
    ]

    out = pulls_from_mc(estimates, stderrs, true_params)

    assert out.pulls == [pytest.approx(2.0)]
    assert out.coverage == 0.0  # |2.0| < 1.0 is False
    assert out.sigma == [0.5]


def test_skips_non_positive_sigma() -> None:
    """Sigma == 0.0 (and negatives) is skipped (would divide by zero)."""
    true_params = {"a": 1.0}
    estimates = [{"a": 1.5}, {"a": 1.5}, {"a": 1.1}]
    stderrs: list[dict[str, float | None]] = [
        {"a": 0.0},  # non-positive → skipped
        {"a": -0.1},  # non-positive → skipped
        {"a": 0.5},  # pull = 0.2
    ]

    out = pulls_from_mc(estimates, stderrs, true_params)

    assert out.pulls == [pytest.approx(0.2)]
    assert out.coverage == 1.0  # |0.2| < 1.0
    assert out.sigma == [0.5]


def test_skips_missing_estimate_keys() -> None:
    """If a true_params key is absent from an estimate dict, it is skipped."""
    true_params = {"a": 1.0, "b": 2.0}
    estimates = [
        {"a": 1.5},  # "b" missing → b skipped this draw
        {"a": 1.0, "b": 2.5},  # both present
    ]
    stderrs: list[dict[str, float | None]] = [
        {"a": 0.5, "b": 0.5},
        {"a": 0.5, "b": 0.5},
    ]

    out = pulls_from_mc(estimates, stderrs, true_params)

    # Sample 1: a only (pull 1.0). Sample 2: a (0.0) + b (1.0).
    assert out.pulls == [1.0, 0.0, 1.0]
    assert out.coverage == pytest.approx(1.0 / 3.0)
    assert out.sigma == [0.5, 0.5]


def test_empty_inputs_returns_none_coverage() -> None:
    """Empty estimates/stderrs → pulls=[0.0], coverage=None (σ-absent), sigma=[0.0].

    Previously this returned coverage=0.0 (EF-PY-06 bug). An empty MC run has no
    valid σ, so coverage is typed-missing (None) to distinguish it from a genuine
    "0% within 1σ" failure.
    """
    out = pulls_from_mc([], [], {"a": 1.0})

    assert isinstance(out, Uncertainty)
    assert out.pulls == [0.0]
    assert out.coverage is None  # was 0.0 — the bug; now None = σ not reported
    assert out.sigma == [0.0]


def test_last_sigma_alphabetical_ordering() -> None:
    """Returned σ list is keys-sorted-alphabetically last-seen σ values."""
    # Insert order in true_params is intentionally NOT alphabetical.
    true_params = {"c": 0.0, "a": 0.0, "b": 0.0}
    estimates = [{"a": 0.0, "b": 0.0, "c": 0.0}, {"a": 0.0, "b": 0.0, "c": 0.0}]
    stderrs: list[dict[str, float | None]] = [
        {"a": 0.1, "b": 0.2, "c": 0.3},  # first pass; will be overwritten
        {"a": 0.7, "b": 0.8, "c": 0.9},  # last seen wins
    ]

    out = pulls_from_mc(estimates, stderrs, true_params)

    # σ list is sorted by key → a, b, c → 0.7, 0.8, 0.9
    assert out.sigma == [0.7, 0.8, 0.9]


def test_iter_valid_pulls_yields_only_valid_tuples() -> None:
    """The private iterator helper yields only (key, sigma, pull) for valid samples."""
    true_params = {"a": 1.0, "b": 2.0}
    estimates = [{"a": 1.5}, {"a": 1.0, "b": 2.5}]
    stderrs: list[dict[str, float | None]] = [
        {"a": 0.5, "b": None},  # b skipped (None)
        {"a": -1.0, "b": 0.5},  # a skipped (non-positive), b valid
    ]

    out = list(_iter_valid_pulls(estimates, stderrs, true_params))

    # Sample 1: only ("a", 0.5, 1.0). Sample 2: only ("b", 0.5, 1.0).
    assert len(out) == 2
    assert out[0] == ("a", 0.5, pytest.approx(1.0))
    assert out[1] == ("b", 0.5, pytest.approx(1.0))


def test_pull_formula_is_estimate_minus_truth_over_sigma() -> None:
    """Sanity-check the pull formula against a hand-computed value."""
    true_params = {"x": 10.0}
    estimates = [{"x": 11.5}]
    stderrs: list[dict[str, float | None]] = [{"x": 0.5}]

    out = pulls_from_mc(estimates, stderrs, true_params)

    # (11.5 - 10.0) / 0.5 = 3.0
    assert out.pulls == [pytest.approx(3.0)]
    assert not math.isclose(out.coverage, 1.0)
    assert out.coverage == 0.0
