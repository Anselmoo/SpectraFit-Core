"""Kowalik–Osborne rational function (NIST StRD MGH09) lineshape recipe."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from . import register_lineshape

if TYPE_CHECKING:
    from oracles.cases import Component


@register_lineshape("mgh09_rational")
def build(rng: random.Random, variant: str) -> tuple[list[Component], str]:
    r"""MGH09 rational lineshape on (0.1-8).

    $\text{amplitude} \cdot (x^2+\text{num\_lin} \cdot x)/(x^2+\text{den\_lin} \cdot x+\text{den\_const})$.
    Denominator coefficients are kept near the MGH09 certified values (num_lin
    $\approx$ 0.19, den_lin $\approx$ 0.12, den_const $\approx$ 0.14) where the
    discriminant $\text{den\_lin}^2 - 4 \cdot \text{den\_const} < 0$, so the
    denominator never vanishes on the positive grid (mirrors the parity test).
    """
    from oracles.cases import Mgh09RationalSpec  # lazy — avoids circular import

    return [
        Mgh09RationalSpec(
            amplitude=round(rng.uniform(2.0, 5.0), 3),
            num_lin=round(rng.uniform(0.15, 0.25), 4),
            den_lin=round(rng.uniform(0.10, 0.15), 4),
            den_const=round(rng.uniform(0.12, 0.18), 4),
        ),
    ], "MGH09 Kowalik-Osborne rational"
