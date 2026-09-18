"""Saturating-exponential (NIST BoxBOD) lineshape recipe."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from . import register_lineshape

if TYPE_CHECKING:
    from oracles.cases import Component


@register_lineshape("saturating_exponential")
def build(rng: random.Random, variant: str) -> tuple[list[Component], str]:
    r"""BoxBOD saturating rise on a positive-x grid (0-8).

    $\text{amplitude} \cdot (1 - \exp(-\text{rate} \cdot x))$.
    Monotone rise toward *amplitude*; ``rate`` stays well away from 0 so the
    curve has real curvature for the solver to recover.
    """
    from oracles.cases import SaturatingExponentialSpec  # lazy — avoids circular import

    return [
        SaturatingExponentialSpec(
            amplitude=round(rng.uniform(3.0, 6.0), 3),
            rate=round(rng.uniform(0.3, 0.8), 3),
        ),
    ], "BoxBOD saturating exponential"
