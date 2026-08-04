"""Zirilli optimization landscape."""

from __future__ import annotations

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("zirilli")
def _zirilli(x: Array) -> Array:
    """1-D Zirilli: ``0.25x⁴ − 0.5x² + 0.1x`` — an asymmetric double well."""
    return 0.25 * x**4 - 0.5 * x**2 + 0.1 * x
