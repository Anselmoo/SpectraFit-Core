"""Ackley optimization landscape."""

from __future__ import annotations

import numpy as np

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("ackley")
def _ackley(x: Array) -> Array:
    """1-D Ackley slice: many shallow local minima around a global basin."""
    return (
        -20.0 * np.exp(-0.2 * np.sqrt(x**2))
        - np.exp(np.cos(2 * np.pi * x))
        + 20.0
        + np.e
    )
