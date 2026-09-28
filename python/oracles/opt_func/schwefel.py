"""Schwefel optimization landscape."""

from __future__ import annotations

import numpy as np

from oracles.opt_func import register_landscape
from oracles.opt_func._types import Array


@register_landscape("schwefel")
def _schwefel(x: Array) -> Array:
    r"""1-D Schwefel slice $418.9829 - x \cdot \sin(\sqrt{|x|})$.

    Deep, deceptive minima.
    """
    return 418.9829 - x * np.sin(np.sqrt(np.abs(x)))
