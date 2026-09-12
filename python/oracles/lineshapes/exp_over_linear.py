"""Exponential decay over a line (NIST StRD Chwirut1/Chwirut2) lineshape recipe."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from . import register_lineshape

if TYPE_CHECKING:
    from oracles.cases import Component


@register_lineshape("exp_over_linear")
def build(rng: random.Random, variant: str) -> tuple[list[Component], str]:
    r"""Chwirut decay over a line, on (0-8).

    $e^{-\text{rate}\cdot x}/(\text{lin\_const}+\text{lin\_slope}\cdot x)$.
    Both denominator coefficients are drawn positive, so on the positive-x grid
    ``lin_const + lin_slope * x`` is monotone increasing from ``lin_const`` — never
    zero. Deliberately not named ``den_const``/``den_lin``: this table is keyed by
    parameter name across every model, and those names belong to mgh09_rational.
    """
    from oracles.cases import ExpOverLinearSpec  # lazy — avoids circular import

    return [
        ExpOverLinearSpec(
            rate=round(rng.uniform(0.3, 0.8), 3),
            lin_const=round(rng.uniform(3.0, 5.0), 3),
            lin_slope=round(rng.uniform(0.3, 0.7), 3),
        ),
    ], "Chwirut1/Chwirut2 exponential over line"
