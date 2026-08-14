"""Bohachevsky optimization landscape."""

from __future__ import annotations

import numpy as np

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("bohachevsky")
def _bohachevsky(x: Array) -> Array:
    r"""1-D Bohachevsky: $x^2 - 0.3 \cdot \cos(3\pi x) + 0.3$ — a bowl with a fine ripple."""
    return x**2 - 0.3 * np.cos(3.0 * np.pi * x) + 0.3
