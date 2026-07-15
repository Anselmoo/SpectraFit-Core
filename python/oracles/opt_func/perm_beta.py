"""Perm(beta) optimization landscape."""

from __future__ import annotations

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("perm_beta")
def _perm_beta(x: Array) -> Array:
    """1-D Perm(β=0.5) slice — a safe, finite shifted-basin form."""
    return ((1.0 / 1.5) * (x - 1.0)) ** 2 + ((1.0 / 2.5) * (x / 2.0 - 1.0)) ** 2
