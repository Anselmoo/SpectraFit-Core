"""Drop-Wave optimization landscape."""

from __future__ import annotations

import numpy as np

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("drop_wave")
def _drop_wave(x: Array) -> Array:
    r"""1-D Drop-Wave $-(1 + \cos(12|x|)) / (\frac{1}{2}x^2 + 2)$.

    Concentric rings.
    """
    return -(1.0 + np.cos(12.0 * np.abs(x))) / (0.5 * x**2 + 2.0)
