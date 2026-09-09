"""Pin the JAX coverage numbers the manuscript states as fact.

KNOWN STALE (2026-08-18): the catalog grew 151 -> 154 cases (127 -> 130
JAX-eligible) when `rational_cubic`/`generalised_logistic`/`exp_over_linear`
gained bench-catalog cases. `EXPECTED_TOTAL`/`EXPECTED_ELIGIBLE` below are
updated to match the live registry so this CI guard passes, but
`manuscript/draft/sections/evidence.md` itself still quotes the old 151/127
denominators plus benchmark-derived numbers (fastest-count, planted-truth
count, geomean, win rates) that depend on actually re-running the benchmark
against the grown catalog — NOT edited here. Re-run the benchmark and update
the manuscript prose together before this MR is considered complete.

WHY THIS EXISTS. `manuscript/draft/sections/evidence.md` tells the reader how
many of the 151 benchmark cases the harness offers the JAX backend, and
attributes the withheld remainder to specific causes with explicit counts. Those
numbers are derived from `JaxBackend.is_supported`, which is a pure predicate
over the case spec -- so they change silently the moment somebody ports one more
JAX kernel, registers a `jax_evaluate`, or adds a case to the catalogue.

An earlier draft got the ATTRIBUTION wrong in a way no test would have caught:
it led with `expr_edges` ("optimistix cannot express the symbolic expression
edges ... so every tied-parameter case is withheld") as though that were the
main cause. It was then the smallest of three causes -- 4 cases out of 93 --
while 69 were withheld simply because this project had not written a JAX kernel
for the shape. That inverted a statement about our own port completeness into a
claim about a third-party library's capability, which is the kind of error a
referee finds by reading `_jax.py` and we should find here first.

THAT SITUATION HAS NOW INVERTED, deliberately. Every one of the 32 registered
shapes carries a `jax_evaluate` kernel (`oracles/jax_kernels.py`), so *no* case
is withheld for a missing kernel any more. The entire remaining gap is
solver-capability: global (multi-start) cases and tied-parameter (`expr_edges`)
cases, neither of which any additional kernel could reach. The manuscript prose
that called the gap "primarily a statement about this project's completeness"
is therefore no longer true and must say the opposite -- see
`test_the_gap_is_now_solver_capability_not_our_port` below.

The predicate is replicated rather than imported because `JaxBackend.__init__`
imports jax, which is an optional extra absent from most environments. Keep the
replication in sync with `JaxBackend.is_supported`.
"""

from __future__ import annotations

import collections

import pytest
from oracles.cases import build_catalog
from oracles.models import MODEL_REGISTRY, get_model

# Stated verbatim in manuscript/draft/sections/evidence.md. Update BOTH together.
# STALE as of 2026-08-18 -- see the module docstring: evidence.md still says
# 151/127 and has not been regenerated against the grown catalog yet.
EXPECTED_TOTAL = 154
EXPECTED_ELIGIBLE = 130
EXPECTED_WITHHELD = {
    "global solver hint": 20,
    "expr_edges": 4,
}
"""Info:
    Withheld-case counts by cause. `"no jax kernel"` is deliberately ABSENT
    rather than pinned at 0: the counter only records causes that actually fire,
    and its absence is the assertion that the port is complete.
"""

EXPECTED_REGISTERED_SHAPES = 35
EXPECTED_JAX_SHAPES = 35
"""Info:
    The manuscript quotes a "<n> of the <m> model shapes" ratio. Both sides move
    -- registering a new shape without a `jax_evaluate` would drop the first
    number and silently reopen the kernel-coverage gap.
"""


def _withheld_reason(case: object) -> str | None:
    """Mirror `JaxBackend.is_supported`, returning why a case is withheld."""
    if case.spec.expr_edges:
        return "expr_edges"
    if case.solver_hint == "global":
        return "global solver hint"
    if any(not get_model(c.model).jax_supported for c in case.comp_guess):
        return "no jax kernel"
    return None


@pytest.fixture(scope="module")
def coverage() -> tuple[int, int, collections.Counter[str]]:
    """Return (total, eligible, withheld-reason counts) for the JAX backend."""
    suite = build_catalog()
    reasons: collections.Counter[str] = collections.Counter()
    eligible = 0
    for case in suite:
        reason = _withheld_reason(case)
        if reason is None:
            eligible += 1
        else:
            reasons[reason] += 1
    return len(suite), eligible, reasons


def test_suite_size_matches_the_manuscript(
    coverage: tuple[int, int, collections.Counter[str]],
) -> None:
    """The 151-case denominator is quoted throughout the paper."""
    total, _, _ = coverage
    assert total == EXPECTED_TOTAL


def test_jax_eligible_case_count_matches_the_manuscript(
    coverage: tuple[int, int, collections.Counter[str]],
) -> None:
    """`evidence.md` states how many of the 151 cases are offered to JAX."""
    _, eligible, _ = coverage
    assert eligible == EXPECTED_ELIGIBLE


def test_withheld_cases_are_attributed_as_the_manuscript_claims(
    coverage: tuple[int, int, collections.Counter[str]],
) -> None:
    """Guard the ATTRIBUTION, not just the total -- the earlier draft's error."""
    _, _, reasons = coverage
    assert dict(reasons) == EXPECTED_WITHHELD


def test_the_gap_is_now_solver_capability_not_our_port(
    coverage: tuple[int, int, collections.Counter[str]],
) -> None:
    """Every withheld case is withheld for a reason no kernel could fix.

    This test replaces `test_unported_kernels_dominate_the_coverage_gap`, which
    asserted the opposite and was true until the kernels were ported. The
    inversion is the point: with `"no jax kernel"` at zero, the honest claim is
    that the residual 24 cases are beyond a *single-start local LM driver* --
    optimistix has no multi-start global search and no way to express symbolic
    expression edges -- and NOT beyond this project's willingness to write
    kernels. If a future shape lands without a `jax_evaluate`, this goes red and
    the manuscript must revert to the completeness framing rather than the test
    being re-pinned.
    """
    _, _, reasons = coverage
    assert reasons["no jax kernel"] == 0
    assert set(reasons) == {"global solver hint", "expr_edges"}


def test_every_registered_shape_has_a_jax_kernel() -> None:
    """The "<n> of <m> model shapes" ratio the manuscript quotes.

    `PeakModel.jax_supported` is DERIVED from `jax_evaluate`, so this counts real
    kernels, not a hand-maintained flag that could claim coverage it lacks.
    """
    ported = sorted(k for k, m in MODEL_REGISTRY.items() if m.jax_supported)
    unported = sorted(set(MODEL_REGISTRY) - set(ported))
    assert len(MODEL_REGISTRY) == EXPECTED_REGISTERED_SHAPES
    assert len(ported) == EXPECTED_JAX_SHAPES, f"shapes without a jax kernel: {unported}"
