"""Levy optimization landscape."""

from __future__ import annotations

import numpy as np

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("levy")
def _levy(x: Array) -> Array:
    """1-D Levy slice: ``sin²(πw) + (w−1)²(1+sin²(2πw))``, ``w = 1 + (x−1)/4``."""
    w = 1.0 + (x - 1.0) / 4.0
    return np.sin(np.pi * w) ** 2 + (w - 1.0) ** 2 * (
        1.0 + np.sin(2.0 * np.pi * w) ** 2
    )
