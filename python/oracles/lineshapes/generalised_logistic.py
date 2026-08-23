"""Generalised logistic / Richards curve (NIST StRD Rat42/Rat43) lineshape recipe."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from . import register_lineshape

if TYPE_CHECKING:
    from oracles.cases import Component


@register_lineshape("generalised_logistic")
def build(rng: random.Random, variant: str) -> tuple[list[Component], str]:
    r"""Generalised logistic $\text{amplitude} / (1+\exp(\text{shift}-\text{rate}\cdot x))^{1/\text{shape}}$.

    Unrestricted domain — $1+\exp(\cdot)$ is positive everywhere, so no x-range
    guard is needed. Parameters mirror the parity-test values (shift=1.2; amplitude,
    rate, shape share the shared parameter table's ranges).
    """
    from oracles.cases import GeneralisedLogisticSpec  # lazy — avoids circular import

    return [
        GeneralisedLogisticSpec(
            amplitude=round(rng.uniform(2.0, 5.0), 3),
            shift=round(rng.uniform(0.8, 1.6), 3),
            rate=round(rng.uniform(0.3, 0.8), 3),
            shape=round(rng.uniform(0.5, 2.0), 3),
        ),
    ], "Rat42/Rat43 generalised logistic"
