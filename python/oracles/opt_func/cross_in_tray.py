"""Cross-in-Tray optimization landscape."""

from __future__ import annotations

import numpy as np

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("cross_in_tray")
def _cross_in_tray(x: Array) -> Array:
    """1-D Cross-in-Tray slice — the ``exp`` argument is clamped to avoid overflow."""
    arg = np.clip(np.abs(100.0 - np.abs(x) / np.pi), None, 50.0)
    return -0.0001 * (np.abs(np.sin(x) * np.exp(arg)) + 1.0) ** 0.1
