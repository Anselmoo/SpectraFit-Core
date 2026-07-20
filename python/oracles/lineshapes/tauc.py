"""Tauc optical band-gap edge lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("tauc")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """Tauc band-gap edge on a positive-energy grid (0.2-8.0).

    p=2 indirect gap, p=1/2 direct gap — drawn from both regimes.
    """
    from oracles.cases import TaucSpec  # lazy — avoids circular import at module load

    return [
        TaucSpec(
            amplitude=round(rng.uniform(0.5, 2.0), 3),
            e_gap=round(rng.uniform(1.5, 3.5), 3),
            exponent=round(rng.choice([0.5, 2.0]) * rng.uniform(0.9, 1.1), 3),
        )
    ], "Tauc band-gap edge"
