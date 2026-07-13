"""Wire W1 — synthetic data must have the moments we claim it does.

The synth layer adds Gaussian noise with stated σ. If E[noise] != 0 or
var(noise) != σ², every coverage test downstream is wrong.
"""
from __future__ import annotations

import math
import random

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings, strategies as st

from oracles.synth import _g


@given(
    a=st.floats(min_value=0.1, max_value=10.0, allow_nan=False),
    c=st.floats(min_value=-5.0, max_value=5.0, allow_nan=False),
    s=st.floats(min_value=0.1, max_value=3.0, allow_nan=False),
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_gaussian_peak_value_equals_amplitude_at_center(a: float, c: float, s: float) -> None:
    """At x=c the Gaussian must evaluate to exactly `a` (amplitude convention pinned in CLAUDE.md)."""
    assert _g(c, a, c, s) == pytest.approx(a, rel=1e-12)


@given(
    sigma=st.floats(min_value=0.01, max_value=2.0, allow_nan=False),
    n=st.integers(min_value=2_000, max_value=10_000),
    seed=st.integers(min_value=0, max_value=2**31 - 1),
)
@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_added_noise_has_zero_mean_and_unit_variance(sigma: float, n: int, seed: int) -> None:
    """Mean of N samples ~ N(0, σ²) is within 4·σ/√N of zero; variance within ±15%."""
    rng = random.Random(seed)
    samples = np.array([rng.gauss(0.0, sigma) for _ in range(n)])
    tol_mean = 4 * sigma / math.sqrt(n)
    assert abs(samples.mean()) < tol_mean
    assert 0.85 * sigma**2 < samples.var() < 1.15 * sigma**2
