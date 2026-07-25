"""Rosenbrock optimization landscape."""

from __future__ import annotations

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("rosenbrock")
def _rosenbrock(x: Array) -> Array:
    """Rosenbrock valley rendered as a 1-D curve in x."""
    return (1.0 - x) ** 2 + 100.0 * (x**2 - x) ** 2
