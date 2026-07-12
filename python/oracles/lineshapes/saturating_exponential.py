"""Saturating-exponential (NIST BoxBOD) lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("saturating_exponential")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """BoxBOD saturating rise ``amplitude·(1−exp(−rate·x))`` on a positive-x grid (0-8).

    Monotone rise toward *amplitude*; ``rate`` stays well away from 0 so the curve
    has real curvature for the solver to recover.
    """
    from oracles.cases import SaturatingExponentialSpec  # lazy — avoids circular import

    return [
        SaturatingExponentialSpec(
            amplitude=round(rng.uniform(3.0, 6.0), 3),
            rate=round(rng.uniform(0.3, 0.8), 3),
        )
    ], "BoxBOD saturating exponential"
