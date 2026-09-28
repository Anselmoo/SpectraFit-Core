"""Sphere optimization landscape."""

from __future__ import annotations

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("sphere")
def _sphere(x: Array) -> Array:
    r"""1-D Sphere: $x^2$ — the canonical convex bowl."""
    return x**2
