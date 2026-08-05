"""Styblinski-Tang optimization landscape."""

from __future__ import annotations

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("styblinski_tang")
def _styblinski_tang(x: Array) -> Array:
    """1-D Styblinski–Tang: ``½(x⁴ − 16x² + 5x)`` — a deceptive double well."""
    return 0.5 * (x**4 - 16.0 * x**2 + 5.0 * x)
