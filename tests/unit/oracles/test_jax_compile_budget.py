"""The jax compiled-executable cache stays bounded, and bounding it moves no number.

WHY THIS EXISTS. Every distinct compiled XLA executable costs mmap regions, jax keeps
them for the life of the process, and the kernel caps a process at ``vm.max_map_count``
mappings. A full benchmark run compiles ~360-384 distinct executables — the analyzed
phase re-fits every case at three extra grid sizes — which crossed the 65530 default cap
and killed every rung of the FAIR reps ladder with ``SIGABRT``/``SIGSEGV``, reported as
"Cannot allocate memory" while peak RSS sat near 2 GB on a 31 GiB host.

:class:`~oracles.backends._jax.JaxBackend` therefore drops its cache every
``compile_budget`` distinct ``(layout, n_points)`` executables. Two things have to hold
for that to be a fix rather than a trade:

1. the mapping count must *plateau* rather than climb with the case count, and
2. dropping the cache must not change a fitted number — a bound that perturbs $r^2$ or
   a recovered parameter would silently corrupt every jax column in the report.

Both are asserted here. The mapping assertion reads ``/proc/self/maps`` and is skipped
where that does not exist, because the count it guards is a Linux kernel limit.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from oracles.cases import BenchCase, build_catalog, materialize

jax = pytest.importorskip("jax")
pytest.importorskip("optimistix")

from oracles.backends import _jax as jx

_MAPS = Path(f"/proc/{os.getpid()}/maps")


def _map_count() -> int:
    """Number of mmap regions this process holds."""
    with _MAPS.open(encoding="utf-8") as fh:
        return sum(1 for _ in fh)


def _distinct_shape_cases(n: int) -> list[BenchCase]:
    """*n* cases that compile to distinct executables (one grid size per case).

    Re-materializing at a fresh ``n_points`` guarantees a distinct
    ``(layout, n_points)`` key even when two catalog cases share a layout, so the
    budget is exercised by exactly ``n`` compilations rather than by however many
    happen to be unique.
    """
    backend = jx.JaxBackend()
    eligible = [c for c in build_catalog() if backend.is_supported(c)]
    out: list[BenchCase] = []
    for i, case in enumerate(eligible[:n]):
        spec = case.spec.model_copy(update={"n_points": 90 + i, "id": f"{case.id}__b{i}"})
        out.append(materialize(spec))
    return out


def test_budget_defaults_and_env_override() -> None:
    """The default is the documented one, and the env var wins over it."""
    assert jx.JaxBackend().compile_budget == jx._DEFAULT_COMPILE_BUDGET
    assert jx.JaxBackend(compile_budget=7).compile_budget == 7


def test_env_override_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """``SPECTRAFIT_BENCH_JAX_COMPILE_BUDGET`` is honoured, and never goes below 1."""
    monkeypatch.setenv(jx._COMPILE_BUDGET_ENV, "9")
    assert jx.JaxBackend().compile_budget == 9
    monkeypatch.setenv(jx._COMPILE_BUDGET_ENV, "0")
    assert jx.JaxBackend().compile_budget == 1


def test_cache_is_cleared_once_the_budget_is_exceeded() -> None:
    """Compiling past the budget trips a clear; staying under it does not."""
    backend = jx.JaxBackend(compile_budget=4)
    cases = _distinct_shape_cases(10)

    for case in cases[:4]:
        backend.run(backend.build(case), case)
    assert backend.n_cache_clears == 0, "cleared before the budget was reached"

    for case in cases[4:]:
        backend.run(backend.build(case), case)
    assert backend.n_cache_clears >= 1, "never cleared despite exceeding the budget"


def test_repeated_shape_is_free() -> None:
    """A key already seen since the last clear must not consume budget.

    This is the reuse ``_residual_for``'s memo exists to obtain: without it, the
    timing loop's ``n_reps`` builds of one case would each count as a compilation and
    a run would clear its cache constantly.
    """
    backend = jx.JaxBackend(compile_budget=2)
    case = _distinct_shape_cases(1)[0]
    for _ in range(10):
        backend.build(case)
    assert backend.n_cache_clears == 0


@pytest.mark.skipif(not _MAPS.exists(), reason="mmap accounting is Linux-only")
def test_mapping_count_plateaus_instead_of_growing() -> None:
    """Mappings must stop growing with the case count — the actual failure mode.

    A leak-free run is not the claim; a *bounded* one is. The count after the second
    batch is allowed to exceed the first (a clear releases lazily), but it must not
    grow in proportion to the number of executables compiled.
    """
    backend = jx.JaxBackend(compile_budget=4)
    cases = _distinct_shape_cases(24)

    for case in cases[:12]:
        backend.run(backend.build(case), case)
    after_first = _map_count()

    for case in cases[12:]:
        backend.run(backend.build(case), case)
    after_second = _map_count()

    growth = after_second - after_first
    assert backend.n_cache_clears >= 2
    assert growth < after_first, (
        f"mappings grew by {growth} over the second batch of 12 "
        f"(first batch reached {after_first}) — the cache is not bounded"
    )


def test_clearing_the_cache_does_not_move_a_fitted_number() -> None:
    """The same case fitted either side of a clear yields identical metrics.

    Guards the half of this change that a benchmark cannot self-report: an unbounded
    run and a bounded one must produce the same report, or the bound has become a
    silent source of measurement drift.
    """
    backend = jx.JaxBackend(compile_budget=1024)
    case = _distinct_shape_cases(1)[0]

    before = backend.extract(backend.run(backend.build(case), case), case)
    jax.clear_caches()
    after = backend.extract(backend.run(backend.build(case), case), case)

    assert after.r2 == pytest.approx(before.r2, rel=0, abs=0)
    assert after.chi2 == pytest.approx(before.chi2, rel=0, abs=0)
    assert after.success == before.success
    assert after.params == before.params


def test_residual_memo_survives_a_clear() -> None:
    """``jax.clear_caches()`` must not be paired with clearing the residual memo.

    The memo keys one callable identity per layout so optimistix compiles once per
    layout instead of re-tracing on every call — the amortization its docstring
    documents. Clearing it was measured to release no mappings, so doing so would cost
    re-tracing for nothing.
    """
    backend = jx.JaxBackend(compile_budget=2)
    for case in _distinct_shape_cases(6):
        backend.run(backend.build(case), case)

    populated = jx._residual_for.cache_info().currsize
    assert populated > 0, "the residual memo was never populated"
    assert backend.n_cache_clears >= 1
    assert jx._residual_for.cache_info().currsize == populated
