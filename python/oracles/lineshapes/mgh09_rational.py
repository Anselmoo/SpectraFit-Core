"""Kowalik–Osborne rational function (NIST StRD MGH09) lineshape recipe."""

from __future__ import annotations

import random

from . import register_lineshape


@register_lineshape("mgh09_rational")
def build(rng: random.Random, variant: str) -> tuple[list, str]:  # noqa: ARG001
    """MGH09 rational ``amplitude·(x²+num_lin·x)/(x²+den_lin·x+den_const)`` on (0.1-8).

    Denominator coefficients are kept near the MGH09 certified values (num_lin≈0.19,
    den_lin≈0.12, den_const≈0.14) where the discriminant ``den_lin²−4·den_const < 0``,
    so the denominator never vanishes on the positive grid (mirrors the parity test).
    """
    from oracles.cases import Mgh09RationalSpec  # lazy — avoids circular import

    return [
        Mgh09RationalSpec(
            amplitude=round(rng.uniform(2.0, 5.0), 3),
            num_lin=round(rng.uniform(0.15, 0.25), 4),
            den_lin=round(rng.uniform(0.10, 0.15), 4),
            den_const=round(rng.uniform(0.12, 0.18), 4),
        )
    ], "MGH09 Kowalik-Osborne rational"
