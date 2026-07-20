"""EF-PY-06 regression: σ-less backends must emit coverage=None, not 0.0.

When every stderr entry is None (jax sets ``param_stderr={k: None}``), the
pulls list is empty and coverage was formerly ``0.0`` — indistinguishable from a
genuine "0 % of params within 1σ" failure. This test pins the corrected contract:
``coverage`` must be ``None`` when no valid σ is available.
"""

from __future__ import annotations

import pytest

from oracles.metrics import pulls_from_mc


def test_sigma_absent_yields_none_coverage_not_zero() -> None:
    """All stderrs None → coverage=None (σ-absent), not 0.0 (genuine failure)."""
    true_params = {"a": 1.0, "b": 2.0}
    estimates = [{"a": 1.5, "b": 2.1}, {"a": 0.9, "b": 2.0}]
    stderrs: list[dict[str, float | None]] = [
        {"a": None, "b": None},
        {"a": None, "b": None},
    ]

    out = pulls_from_mc(estimates, stderrs, true_params)

    assert out.coverage is None, (
        f"Expected coverage=None for σ-absent backend, got {out.coverage!r}. "
        "coverage=0.0 is indistinguishable from a genuine '0% coverage' failure."
    )


def test_sigma_absent_empty_inputs_yields_none_coverage() -> None:
    """Empty estimates/stderrs (zero MC fits) → coverage=None."""
    out = pulls_from_mc([], [], {"a": 1.0})

    assert out.coverage is None, (
        f"Expected coverage=None for empty MC inputs, got {out.coverage!r}."
    )


def test_genuine_zero_coverage_remains_float_zero() -> None:
    """σ IS available but all pulls |p|≥1 → coverage=0.0 (real failure, not absent)."""
    true_params = {"a": 1.0}
    estimates = [{"a": 3.0}]  # pull = (3.0 - 1.0) / 0.5 = 4.0  (|4.0| ≥ 1)
    stderrs: list[dict[str, float | None]] = [{"a": 0.5}]

    out = pulls_from_mc(estimates, stderrs, true_params)

    assert out.coverage == pytest.approx(0.0)
    assert out.coverage is not None, (
        "coverage=0.0 (genuine no-coverage-within-1σ) must remain 0.0, not None."
    )


def test_partial_none_sigma_uses_only_valid_samples() -> None:
    """Some σ are None, some are valid → coverage computed from valid ones only, not None."""
    true_params = {"a": 1.0}
    estimates = [{"a": 1.2}, {"a": 3.0}]
    stderrs: list[dict[str, float | None]] = [
        {"a": None},  # skipped
        {"a": 0.5},  # pull = (3.0 - 1.0)/0.5 = 4.0, |4.0| ≥ 1 → not within 1σ
    ]

    out = pulls_from_mc(estimates, stderrs, true_params)

    # At least one valid σ → coverage is a real float (0.0 in this case)
    assert out.coverage is not None
    assert out.coverage == pytest.approx(0.0)
