"""Shared Pydantic contracts between oracles and benchmark.

Holds types that BOTH oracles and benchmark refer to. After Plan H,
``SolverMeta`` lives here (was in extras/bench/contract.py pre-H).
Future shared types accumulate here so neither side becomes the
dumping ground for cross-cutting schema.

Plan H H4.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _Contract(BaseModel):
    """Base for oracles/benchmark shared contracts.

    Camel-case wire form via alias_generator; populate_by_name=True
    lets Python code construct with snake_case while JSON wire uses
    camelCase. extra="forbid" pins the schema strictly.
    """

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class SolverMeta(_Contract):
    """Solver legend entry (id, label, and theme color tokens).

    Re-exported from oracles.bench_contract for BenchReport.solvers.
    """

    id: str
    label: str
    color: str
    soft: str
