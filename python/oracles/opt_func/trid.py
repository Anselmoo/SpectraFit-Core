"""Trid optimization landscape."""

from __future__ import annotations

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("trid")
def _trid(x: Array) -> Array:
    """1-D Trid: ``(x − 1)²`` — shifted bowl."""
    return (x - 1.0) ** 2
