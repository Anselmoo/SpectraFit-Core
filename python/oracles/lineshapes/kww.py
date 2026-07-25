"""KWW (Kohlrausch-Williams-Watts) stretched exponential lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("kww")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """KWW stretched-exponential relaxation on a positive-time grid (0-10)."""
    from oracles.cases import KwwSpec  # lazy — avoids circular import at module load

    return [
        KwwSpec(
            amplitude=round(rng.uniform(3.0, 6.0), 3),
            tau=round(rng.uniform(1.5, 4.0), 3),
            beta=round(rng.uniform(0.4, 0.9), 3),
        )
    ], "KWW stretched exponential"
