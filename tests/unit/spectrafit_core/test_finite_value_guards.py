"""Boundary value guards on FitResult (Invariant V, V2/V4).

A FitResult must not carry a value that is mathematically impossible or
structurally inconsistent — the contract should refuse to construct in such a
state rather than let a corrupt number flow downstream to a panel.

Scope is deliberately conservative (see the value-provenance plan): `explain()`
intentionally tolerates non-finite `reduced_chi2` / `condition_number`
(dof ≤ 0 and non-estimable covariance are legitimate degenerate states), and
serde already maps NaN/Inf → JSON null → a Pydantic type error. So these guards
target only the truly-impossible and the cross-field lock-step invariants of the
per-iteration trajectory wire.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from spectrafit_core.result import FitResult


def _valid_kwargs(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "chi2": 1.2,
        "reduced_chi2": 0.6,
        "r_squared": 0.999,
        "dof": 100,
    }
    base.update(overrides)
    return base


def test_valid_result_constructs() -> None:
    FitResult(**_valid_kwargs())


def test_r_squared_above_one_is_rejected() -> None:
    # R² ≤ 1 always; a value above 1 is impossible (corruption).
    with pytest.raises(ValidationError):
        FitResult(**_valid_kwargs(r_squared=1.0001))


def test_r_squared_exactly_one_is_allowed() -> None:
    # R² == 1 is a legitimate perfect fit (e.g. SS_tot == 0 → r2_of returns 1.0).
    FitResult(**_valid_kwargs(r_squared=1.0))


def test_negative_r_squared_is_allowed() -> None:
    # R² < 0 (worse than the mean) is a legitimate poor fit, not corruption.
    FitResult(**_valid_kwargs(r_squared=-3.0))


def test_negative_chi2_is_rejected() -> None:
    # χ² is a sum of squared residuals — never negative.
    with pytest.raises(ValidationError):
        FitResult(**_valid_kwargs(chi2=-0.1))


def test_negative_dof_is_allowed() -> None:
    # dof < 0 is a legitimate over-parameterized/degenerate state (explain()
    # tolerates the resulting non-finite reduced_chi2) — must NOT be rejected.
    FitResult(**_valid_kwargs(dof=-2, reduced_chi2=float("inf")))


def test_params_history_must_match_cost_history_length() -> None:
    # The faer LM driver records θ lock-step with cost; a length mismatch means
    # the trajectory wire is corrupt.
    with pytest.raises(ValidationError):
        FitResult(
            **_valid_kwargs(
                cost_history=[1.0, 0.5, 0.1],
                params_history=[[1.0, 2.0], [1.1, 2.1]],  # 2 != 3
            )
        )


def test_ragged_params_history_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FitResult(
            **_valid_kwargs(
                cost_history=[1.0, 0.5],
                params_history=[[1.0, 2.0], [1.1]],  # ragged
            )
        )


def test_consistent_trajectory_constructs() -> None:
    FitResult(
        **_valid_kwargs(
            cost_history=[1.0, 0.5, 0.1],
            params_history=[[1.0, 2.0], [1.1, 2.1], [1.2, 2.2]],
        )
    )


def test_empty_histories_are_fine() -> None:
    # Solvers that do not track θ (VarPro, lm-legacy) leave both empty.
    FitResult(**_valid_kwargs(cost_history=[], params_history=[]))


def test_params_history_without_cost_history_is_rejected() -> None:
    # θ recorded but no cost recorded ⇒ the lock-step wire is broken.
    with pytest.raises(ValidationError):
        FitResult(**_valid_kwargs(cost_history=[], params_history=[[1.0]]))
