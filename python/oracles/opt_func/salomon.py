"""Salomon optimization landscape."""

from __future__ import annotations

import numpy as np

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("salomon")
def _salomon(x: Array) -> Array:
    """1-D Salomon: ``1 − cos(2π|x|) + 0.1|x|`` — concentric ridges."""
    return 1.0 - np.cos(2.0 * np.pi * np.abs(x)) + 0.1 * np.abs(x)
