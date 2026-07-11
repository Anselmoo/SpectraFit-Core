"""Split (asymmetric) Gaussian lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("split_gauss")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """Split (asymmetric) Gaussian peak — different width on each side."""
    from oracles.cases import SplitGaussianSpec  # lazy — avoids circular import at module load

    return [
        SplitGaussianSpec(
            amplitude=round(rng.uniform(3.0, 6.0), 3),
            center=round(rng.uniform(-1.0, 1.0), 3),
            sigma_l=round(rng.uniform(0.5, 0.9), 3),
            sigma_r=round(rng.uniform(1.0, 1.6), 3),
        )
    ], "split (asymmetric) Gaussian"
