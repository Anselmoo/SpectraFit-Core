"""Benchmark and oracle harness: scenarios, synthetic data, V&V.

Not shipped in the wheel.
"""

from __future__ import annotations

# Intentionally empty: every submodule is imported directly by its own dotted
# path (``from oracles.api import app``, ``from oracles.cases import ...``);
# the package itself re-exports nothing.
__all__: tuple[str, ...] = ()
