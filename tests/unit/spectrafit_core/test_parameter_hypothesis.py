"""Hypothesis property-based tests for Parameter validator edge cases.

Covers:
- Closed-interval boundary values (value == min, value == max)
- Arbitrary valid values inside [lo, hi]
- Rejection of value below min and above max
- Rejection of inverted bounds (min > max)
- Non-empty expr acceptance and whitespace/empty expr rejection
- expr=None always valid
"""

from __future__ import annotations

import pytest
from hypothesis import assume, given, settings, strategies as st
from pydantic import ValidationError

from spectrafit_core.parameters import Parameter


@given(min_v=st.floats(allow_nan=False, min_value=-1e10, max_value=1e10))
@settings(max_examples=100)
def test_value_at_min_bound_is_valid(min_v: float) -> None:
    # value == min must succeed (closed interval)
    Parameter(value=min_v, min=min_v, max=min_v + 1.0)


@given(max_v=st.floats(allow_nan=False, min_value=-1e10, max_value=1e10))
@settings(max_examples=100)
def test_value_at_max_bound_is_valid(max_v: float) -> None:
    # value == max must succeed (closed interval)
    Parameter(value=max_v, min=max_v - 1.0, max=max_v)


@given(
    lo=st.floats(allow_nan=False, min_value=-1e9, max_value=0.0),
    hi=st.floats(allow_nan=False, min_value=0.0, max_value=1e9),
    frac=st.floats(allow_nan=False, min_value=0.0, max_value=1.0),
)
@settings(max_examples=100)
def test_value_in_bounds_is_valid(lo: float, hi: float, frac: float) -> None:
    # value = lo + frac*(hi-lo) is always in [lo, hi]
    assume(hi >= lo)
    value = lo + frac * (hi - lo)
    assume(lo <= value <= hi)  # guard against float rounding
    Parameter(value=value, min=lo, max=hi)


@given(
    base=st.floats(allow_nan=False, min_value=-1e9, max_value=1e9),
    gap=st.floats(allow_nan=False, min_value=1e-6, max_value=1e6),
)
@settings(max_examples=100)
def test_value_below_min_is_rejected(base: float, gap: float) -> None:
    # value = base, min = base + gap → value is below min
    with pytest.raises(ValidationError):
        Parameter(value=base, min=base + gap, max=base + gap + 1.0)


@given(
    base=st.floats(allow_nan=False, min_value=-1e9, max_value=1e9),
    gap=st.floats(allow_nan=False, min_value=1e-6, max_value=1e6),
)
@settings(max_examples=100)
def test_value_above_max_is_rejected(base: float, gap: float) -> None:
    # value = base + gap + 1.0, max = base → value is above max
    with pytest.raises(ValidationError):
        Parameter(value=base + gap + 1.0, min=base - 1.0, max=base)


@given(
    lo=st.floats(allow_nan=False, min_value=-1e9, max_value=1e9),
    gap=st.floats(allow_nan=False, min_value=1e-6, max_value=1e6),
)
@settings(max_examples=100)
def test_inverted_bounds_rejected(lo: float, gap: float) -> None:
    # min = lo + gap, max = lo → min > max, always invalid
    with pytest.raises(ValidationError):
        Parameter(value=lo, min=lo + gap, max=lo)


@given(expr=st.text(min_size=1, alphabet=st.characters(blacklist_categories=("C",))))
@settings(max_examples=50)
def test_nonempty_expr_is_valid(expr: str) -> None:
    assume(expr.strip())  # skip whitespace-only strings
    Parameter(value=0.0, expr=expr)


@given(ws=st.text(alphabet=" \t\n\r", min_size=0, max_size=10))
@settings(max_examples=50)
def test_empty_or_whitespace_expr_rejected(ws: str) -> None:
    # empty string and whitespace-only strings are always invalid as expr
    with pytest.raises(ValidationError):
        Parameter(value=0.0, expr=ws)


def test_expr_none_always_valid() -> None:
    p = Parameter(value=0.0, expr=None)
    assert p.expr is None
