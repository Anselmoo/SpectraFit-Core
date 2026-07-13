"""Griewank optimization landscape."""

from __future__ import annotations

import numpy as np

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("griewank")
def _griewank(x: Array) -> Array:
    """1-D Griewank slice: a broad quadratic with fine oscillations."""
    return x**2 / 4000.0 - np.cos(x) + 1.0
