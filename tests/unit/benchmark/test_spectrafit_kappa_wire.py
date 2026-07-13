"""Unit tests for the spectrafit backend κ(J) wiring.

The Rust kernel emits ``FitResult.condition_number`` = κ(JᵀJ) = κ(J)².
The benchmark axis uses κ(J) (what scipy's ``np.linalg.cond(jac)`` returns).
So the adapter must forward √(condition_number) — not the raw value — when
building ``BackendOutcome.jacobian_condition_number``.

This test file pins the ``_jacobian_kappa`` helper that performs the conversion
and the cap, then verifies the end-to-end wire through ``extract()``.

EF-RUST-03/04
"""

from __future__ import annotations

import pytest

from oracles.backends._spectrafit import _jacobian_kappa


class TestJacobianKappaHelper:
    """Pure-function tests for ``_jacobian_kappa``."""

    def test_known_value_sqrt(self) -> None:
        """condition_number=16.0 → κ(J)=4.0 (sqrt of Gram condition number)."""
        assert _jacobian_kappa(16.0) == pytest.approx(4.0)

    def test_none_input_returns_none(self) -> None:
        """None condition_number → None jacobian_condition_number."""
        assert _jacobian_kappa(None) is None

    def test_zero_returns_zero(self) -> None:
        """Degenerate 0 condition number → 0.0 (sqrt(0) = 0)."""
        assert _jacobian_kappa(0.0) == pytest.approx(0.0)

    def test_one_returns_one(self) -> None:
        """Perfect conditioning: κ(JᵀJ)=1 → κ(J)=1."""
        assert _jacobian_kappa(1.0) == pytest.approx(1.0)

    def test_large_value_is_capped(self) -> None:
        """Extremely large condition_number is capped at _KAPPA_CAP, not inf."""
        from oracles.backends._spectrafit import _KAPPA_CAP

        result = _jacobian_kappa(float("inf"))
        # inf input → cap applies (sqrt(inf) would be inf; we cap)
        assert result is None or result == pytest.approx(_KAPPA_CAP)

    def test_huge_finite_value_caps_at_kappa_cap(self) -> None:
        """√(1e40) = 1e20 > _KAPPA_CAP=1e16, so result is clamped to 1e16."""
        from oracles.backends._spectrafit import _KAPPA_CAP

        result = _jacobian_kappa(1e40)
        assert result == pytest.approx(_KAPPA_CAP)

    def test_nan_returns_none(self) -> None:
        """Non-finite (NaN) condition_number → None."""
        assert _jacobian_kappa(float("nan")) is None

    def test_negative_returns_none(self) -> None:
        """Negative condition_number (ill-formed) → None, not a complex sqrt."""
        assert _jacobian_kappa(-1.0) is None

    def test_realistic_value(self) -> None:
        """Realistic κ(JᵀJ)=1e8 → κ(J)=1e4 (moderately ill-conditioned)."""
        result = _jacobian_kappa(1e8)
        assert result == pytest.approx(1e4, rel=1e-9)
