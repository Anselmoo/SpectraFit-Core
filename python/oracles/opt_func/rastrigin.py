"""Rastrigin optimization landscape."""

from __future__ import annotations

import numpy as np

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("rastrigin")
def _rastrigin(x: Array) -> Array:
    """1-D Rastrigin slice: a regular lattice of local minima."""
    return 10.0 + x**2 - 10.0 * np.cos(2.0 * np.pi * x)
