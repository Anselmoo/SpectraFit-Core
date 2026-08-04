"""Single asymmetric-peak lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("single")
def build(rng: random.Random, variant: str) -> tuple[list, str]:
    """One single asymmetric peak; variant names the model."""
    from oracles.cases import _asym  # lazy — avoids circular import at module load

    m = variant
    return [
        _asym(
            rng,
            m,
            rng.uniform(3.0, 6.0),
            rng.uniform(-1.0, 1.0),
            rng.uniform(0.6, 1.2),
        )
    ], f"single {m}"
