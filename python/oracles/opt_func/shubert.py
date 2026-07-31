"""Shubert optimization landscape."""

from __future__ import annotations

import numpy as np

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("shubert")
def _shubert(x: Array) -> Array:
    """1-D Shubert: ``Σ_{i=1..5} i·cos((i+1)x + i)`` — many global minima."""
    return sum(i * np.cos((i + 1) * x + i) for i in range(1, 6))
