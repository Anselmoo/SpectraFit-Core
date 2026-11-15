"""Shrink-only known-failure list for the ``benchmark_gate`` regression gate.

An entry names one suite case whose regression is accepted as a correctly
reported failure, the issue that tracks it, and the condition under which the
entry must be removed. The gate treats each entry in one of three ways:

- ``failing``: the case is in the run's regression list. It is reported as a
  known failure and is not counted on the ``regressions`` axis.
- ``passing``: the case ran and did not regress. The gate fails with
  ``remove <case> from the known-failure list (<issue>)``, so the list can only
  shrink and never goes stale.
- ``not_in_run``: the run carries no evidence for the case. It is reported and
  neither counted nor failed.

Gate thresholds are not affected by this list.

Example:
    >>> [kf.case_id for kf in KNOWN_FAILURES]
    ['CX-009', 'CX-010', 'CX-014', 'CX-015', 'CX-017', 'CX-020']
    >>> entry = KnownFailure(
    ...     case_id="OF-014",
    ...     issue="#93",
    ...     failure_class="non_stationary_stop",
    ...     removal_condition="RSS within the gate tolerance",
    ... )
    >>> effective, results = classify_known_failures(
    ...     ["OF-001", "OF-014"], frozenset({"OF-001", "OF-014"}), (entry,)
    ... )
    >>> effective
    ['OF-001']
    >>> [(r.entry.case_id, r.status) for r in results]
    [('OF-014', 'failing')]
    >>> stale_entry_message(entry)
    'remove OF-014 from the known-failure list (#93)'
"""

from __future__ import annotations

from collections.abc import Collection, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

KnownFailureStatus = Literal["failing", "passing", "not_in_run"]
"""Outcome of one known-failure entry against one run (see the module docstring)."""

KnownFailureClass = Literal["non_stationary_stop", "stationary_refused_by_gate"]
"""Why the case fails, as measured at its default-path end point.

- ``non_stationary_stop``: the solver stops at a point whose Gauss-Newton
  predicted decrease exceeds $10^{-6}$ of the RSS (central-difference Jacobian,
  components at an active bound by the $10^{-4}$ rule held), and reports
  ``success=False`` for it.
- ``stationary_refused_by_gate``: the end point is stationary by that measure,
  but the success gate holds a component only within $10^{-12}$ of its bound and
  therefore reports ``success=False``.
"""

_NON_STATIONARY_REMOVAL = (
    "the default-path end point is stationary (Gauss-Newton predicted decrease <= 1e-6 "
    "of the RSS, active bounds by the 1e-4 rule) and the fit reports success=True"
)
_HELD_RULE_REMOVAL = (
    "the success gate holds components at an active bound by the 1e-4 rule, so the "
    "stationary end point reports success=True"
)


class KnownFailure(BaseModel):
    """One accepted, correctly reported failure of a single suite case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    issue: str
    failure_class: KnownFailureClass
    removal_condition: str


KNOWN_FAILURES: tuple[KnownFailure, ...] = (
    KnownFailure(
        case_id="CX-009",
        issue="#93",
        failure_class="non_stationary_stop",
        removal_condition=_NON_STATIONARY_REMOVAL,
    ),
    KnownFailure(
        case_id="CX-010",
        issue="#93",
        failure_class="stationary_refused_by_gate",
        removal_condition=_HELD_RULE_REMOVAL,
    ),
    KnownFailure(
        case_id="CX-014",
        issue="#93",
        failure_class="non_stationary_stop",
        removal_condition=_NON_STATIONARY_REMOVAL,
    ),
    KnownFailure(
        case_id="CX-015",
        issue="#93",
        failure_class="non_stationary_stop",
        removal_condition=_NON_STATIONARY_REMOVAL,
    ),
    KnownFailure(
        case_id="CX-017",
        issue="#93",
        failure_class="non_stationary_stop",
        removal_condition=_NON_STATIONARY_REMOVAL,
    ),
    KnownFailure(
        case_id="CX-020",
        issue="#93",
        failure_class="non_stationary_stop",
        removal_condition=_NON_STATIONARY_REMOVAL,
    ),
)
"""The shrink-only list. An entry is added only by an explicit decision and is
removed as soon as the gate reports it as passing. The six complex-category
entries are the cases whose default-path fits report ``success=False`` under the
stationarity gate on ``success`` (#93); before that gate the same end points were
reported as successes."""


class KnownFailureResult(BaseModel):
    """One list entry together with its status in the evaluated run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entry: KnownFailure
    status: KnownFailureStatus


def stale_entry_message(entry: KnownFailure) -> str:
    """Return the gate failure line for an entry whose case no longer fails."""
    return f"remove {entry.case_id} from the known-failure list ({entry.issue})"


def classify_known_failures(
    regression_ids: Sequence[str],
    run_case_ids: Collection[str] | None,
    known_failures: Sequence[KnownFailure] = KNOWN_FAILURES,
) -> tuple[list[str], list[KnownFailureResult]]:
    """Split a run's regressions into gating regressions and known failures.

    Returns ``(effective_regression_ids, results)``. ``effective_regression_ids``
    keeps the input order and drops every listed case. ``results`` holds one
    entry per list item, in list order. ``run_case_ids`` is the set of case ids
    the run evaluated; when it is ``None`` no listed case can be called
    ``passing``, because absence from the regression list alone is not
    evidence that the case ran.
    """
    listed = {kf.case_id for kf in known_failures}
    regressed = set(regression_ids)
    effective = [cid for cid in regression_ids if cid not in listed]
    results: list[KnownFailureResult] = []
    for kf in known_failures:
        status: KnownFailureStatus = "not_in_run"
        if kf.case_id in regressed:
            status = "failing"
        elif run_case_ids is not None and kf.case_id in run_case_ids:
            status = "passing"
        results.append(KnownFailureResult(entry=kf, status=status))
    return effective, results
