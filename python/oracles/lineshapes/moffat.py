"""Moffat peak lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("moffat")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """Moffat peak (beta tail-weight parameter)."""
    from oracles.cases import MoffatSpec  # lazy — avoids circular import at module load

    return [
        MoffatSpec(
            amplitude=round(rng.uniform(3.0, 6.0), 3),
            center=round(rng.uniform(-1.0, 1.0), 3),
            sigma=round(rng.uniform(0.6, 1.1), 3),
            beta=round(rng.uniform(1.2, 4.0), 3),
        )
    ], "Moffat peak"
