"""Egg-Holder optimization landscape."""

from __future__ import annotations

import numpy as np

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("egg_holder")
def _egg_holder(x: Array) -> Array:
    """1-D Egg-Holder slice: ``−(x+47)·sin(√|x/2+47|)`` — deceptive, many minima."""
    return -(x + 47.0) * np.sin(np.sqrt(np.abs(0.5 * x + 47.0)))
