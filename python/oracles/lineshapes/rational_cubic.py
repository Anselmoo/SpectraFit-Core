"""Rational cubic over cubic (NIST StRD Kirby2/Hahn1/Thurber) lineshape recipe."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from . import register_lineshape

if TYPE_CHECKING:
    from oracles.cases import Component


@register_lineshape("rational_cubic")
def build(rng: random.Random, variant: str) -> tuple[list[Component], str]:
    r"""Rational cubic $(a_0+a_1x+a_2x^2+a_3x^3)/(1+b_1x+b_2x^2+b_3x^3)$ on (-4-8).

    Coefficients are drawn in tight bands around the parity-test values (a0=1.2,
    a1=0.3, a2=0.15, a3=0.02, b1=0.05, b2=0.02, b3=0.001), where the denominator's
    only interior stationary point (x $\approx$ -1.4) stays well above zero across
    the whole sampled box — the denominator constant is pinned at 1 (see
    ``oracles.models.rational_cubic``), so it is never a fit parameter.
    """
    from oracles.cases import RationalCubicSpec  # lazy — avoids circular import

    return [
        RationalCubicSpec(
            a0=round(rng.uniform(1.0, 1.4), 3),
            a1=round(rng.uniform(0.2, 0.4), 3),
            a2=round(rng.uniform(0.1, 0.2), 3),
            a3=round(rng.uniform(0.0, 0.04), 4),
            b1=round(rng.uniform(0.03, 0.07), 4),
            b2=round(rng.uniform(0.01, 0.03), 4),
            b3=round(rng.uniform(0.0005, 0.0015), 5),
        ),
    ], "Kirby2/Hahn1/Thurber rational cubic"
