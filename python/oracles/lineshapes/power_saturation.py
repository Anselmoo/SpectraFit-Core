"""Power-law saturation (NIST Misra1b) lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("power_saturation")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """Misra1b saturation ``amplitude·(1−(1+rate·x/2)^(−2))`` on a positive-x grid (0-8).

    ``rate`` is kept in [0.3, 0.6] so ``1 + rate·x/2 > 0`` holds across the grid
    (mirrors the parity-test rate≈0.4 safe value); no negative-base power.
    """
    from oracles.cases import PowerSaturationSpec  # lazy — avoids circular import

    return [
        PowerSaturationSpec(
            amplitude=round(rng.uniform(3.0, 6.0), 3),
            rate=round(rng.uniform(0.3, 0.6), 3),
        )
    ], "Misra1b power saturation"
