"""Alpine N.1 optimization landscape."""

from __future__ import annotations

import numpy as np

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("alpine")
def _alpine(x: Array) -> Array:
    """1-D Alpine N.1: ``|x·sin(x) + 0.1·x|`` — non-smooth multimodal."""
    return np.abs(x * np.sin(x) + 0.1 * x)
