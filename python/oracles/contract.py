"""Cross-cutting Pydantic contract types shared within ``oracles``.

Holds types such as ``SolverMeta`` that several ``oracles`` modules import.
Cross-cutting schema accumulates here so no single module becomes the
dumping ground for it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _Contract(BaseModel):
    """Base for oracles/benchmark shared contracts.

    Camel-case wire form via alias_generator; populate_by_name=True
    lets Python code construct with snake_case while JSON wire uses
    camelCase. extra="forbid" pins the schema strictly.
    """

    model_config = ConfigDict(
        extra="forbid",
        alias_generator=to_camel,
        populate_by_name=True,
    )


class SolverMeta(_Contract):
    """Solver legend entry (id, label, and theme color tokens).

    Re-exported from oracles.bench_contract for BenchReport.solvers.
    """

    id: str = Field(
        description=(
            "Stable backend/solver key (e.g. `spectrafit`, `lmfit`, "
            "`scipy-ls-trf`) used to join this entry against per-backend "
            "results elsewhere in the report."
        ),
    )
    label: str = Field(
        description="Human-readable display name shown in legends and tables.",
    )
    color: str = Field(
        description=(
            "Primary theme color token (CSS `var(--c-...)` reference, with an "
            "optional CSS fallback) used for this backend's main chart marks."
        ),
    )
    soft: str = Field(
        description=(
            "Muted/soft variant of `color` (CSS `var(--c-...-soft)` reference) "
            "used for secondary chart elements — bands, fills, and de-emphasized "
            "series — that must read as the same backend without competing with "
            "the primary marks."
        ),
    )
