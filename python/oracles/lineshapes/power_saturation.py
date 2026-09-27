"""Power-law saturation (NIST Misra1b) lineshape recipe."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from . import register_lineshape

if TYPE_CHECKING:
    from oracles.cases import Component


@register_lineshape("power_saturation")
def build(rng: random.Random, variant: str) -> tuple[list[Component], str]:
    r"""Misra1b saturation on a positive-x grid (0-8).

    $\text{amplitude} \cdot (1-(1+\text{rate} \cdot x/2)^{-2})$.
    ``rate`` is kept in [0.3, 0.6] so $1 + \text{rate} \cdot x/2 > 0$ holds across the grid
    (mirrors the parity-test rate $\approx$ 0.4 safe value); no negative-base power.
    """
    from oracles.cases import PowerSaturationSpec  # lazy — avoids circular import

    return [
        PowerSaturationSpec(
            amplitude=round(rng.uniform(3.0, 6.0), 3),
            rate=round(rng.uniform(0.3, 0.6), 3),
        ),
    ], "Misra1b power saturation"
