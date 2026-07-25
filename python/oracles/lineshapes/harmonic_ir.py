"""Driven damped harmonic-oscillator IR absorption lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("harmonic_ir")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """Driven damped harmonic-oscillator IR absorption."""
    from oracles.cases import (
        HarmonicIrSpec,
    )  # lazy — avoids circular import at module load

    return [
        HarmonicIrSpec(
            amplitude=round(rng.uniform(8.0, 16.0), 3),
            center=round(rng.uniform(2.5, 3.5), 3),
            sigma=round(rng.uniform(0.5, 1.0), 3),
        )
    ], "harmonic IR oscillator"
