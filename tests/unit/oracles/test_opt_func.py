"""Test suite for optimization-landscape functions in oracles.opt_func."""

from __future__ import annotations

import numpy as np
import pytest

from oracles.opt_func import LANDSCAPE_REGISTRY

_LANDSCAPE_KEYS: list[str] = [
    "ackley",
    "alpine",
    "bohachevsky",
    "cosine_mixture",
    "cross_in_tray",
    "drop_wave",
    "egg_holder",
    "griewank",
    "levy",
    "perm_beta",
    "rastrigin",
    "rosenbrock",
    "salomon",
    "schwefel",
    "shubert",
    "sphere",
    "styblinski_tang",
    "sum_squares",
    "trid",
    "zirilli",
]

_X = np.linspace(-4.0, 4.0, 50, dtype=np.float64)


def test_registry_contains_all_expected_keys() -> None:
    """Assert the registry contains exactly the expected landscape keys."""
    assert set(LANDSCAPE_REGISTRY.keys()) == set(_LANDSCAPE_KEYS)


@pytest.mark.parametrize("key", _LANDSCAPE_KEYS)
def test_landscape_returns_finite_array(key: str) -> None:
    """Test that each landscape returns a finite array matching input shape.

    Parametrized over all registered landscape keys.
    """
    fn = LANDSCAPE_REGISTRY[key]
    y = fn(_X)
    assert y.shape == _X.shape, (
        f"Shape mismatch for {key}: got {y.shape}, expected {_X.shape}"
    )
    assert np.all(np.isfinite(y)), f"Non-finite values in {key} output"


def test_sphere_known_minimum() -> None:
    """Test that sphere function has minimum at x=0 with value 0.0."""
    fn = LANDSCAPE_REGISTRY["sphere"]
    assert fn(np.array([0.0]))[0] == pytest.approx(0.0)


def test_rastrigin_known_minimum() -> None:
    """Test that Rastrigin function has minimum at x=0 with value 0.0."""
    fn = LANDSCAPE_REGISTRY["rastrigin"]
    assert fn(np.array([0.0]))[0] == pytest.approx(0.0, abs=1e-10)
