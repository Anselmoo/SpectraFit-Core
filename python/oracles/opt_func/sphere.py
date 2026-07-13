"""Sphere optimization landscape."""

from __future__ import annotations

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("sphere")
def _sphere(x: Array) -> Array:
    """1-D Sphere: ``x²`` — the canonical convex bowl."""
    return x**2
