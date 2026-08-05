"""Cosine-Mixture optimization landscape."""

from __future__ import annotations

import numpy as np

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("cosine_mixture")
def _cosine_mixture(x: Array) -> Array:
    """1-D Cosine-Mixture: ``x² − 0.1·cos(5πx)`` — a bowl with a fine cosine ripple."""
    return x**2 - 0.1 * np.cos(5.0 * np.pi * x)
