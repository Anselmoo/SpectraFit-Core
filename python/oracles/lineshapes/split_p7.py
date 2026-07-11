"""Split Pearson VII lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("split_p7")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """Split Pearson VII peak (split width + exponent each side)."""
    from oracles.cases import SplitPearson7Spec  # lazy — avoids circular import at module load

    return [
        SplitPearson7Spec(
            amplitude=round(rng.uniform(3.0, 6.0), 3),
            center=round(rng.uniform(-1.0, 1.0), 3),
            sigma_l=round(rng.uniform(0.5, 0.9), 3),
            sigma_r=round(rng.uniform(1.0, 1.6), 3),
            m_l=round(rng.uniform(1.2, 3.0), 3),
            m_r=round(rng.uniform(2.0, 4.0), 3),
        )
    ], "split Pearson VII"
