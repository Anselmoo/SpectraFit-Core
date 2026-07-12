"""Sum-Squares optimization landscape."""

from __future__ import annotations

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("sum_squares")
def _sum_squares(x: Array) -> Array:
    """1-D Sum-Squares: ``2·x²`` — a weighted convex bowl (distinct from Sphere)."""
    return 2.0 * x**2
