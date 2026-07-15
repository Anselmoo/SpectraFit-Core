"""Ground-truth invariants for the benchmark report — prove the JSON is REAL.

These tests encode the properties a ``BenchReport`` must hold for the ``web/`` UI to be
trustworthy, and would have caught the two historical failures that broke the report:

* **run_002** analyzed 119 cases but **dropped all 20 ``optfn``** — a category present in
  ``suite`` was absent from ``analyzed`` (deep-dive). ``test_analyzed_covers_suite_categories``
  + the Tier-2 ``test_full_catalog_is_deep_dived`` guard against it.
* **synth.py** is a single-analyzed-case mockup (``RL-031``); combined with the old web
  ``?? PRIMARY`` fallback it rendered *every* case identically. ``test_analyzed_is_multiple``
  and the plot-distinctness tests guard against it.

Two tiers:

* **Tier 1 (fast, CI default)** — ``engine.build_report`` on a tiny injected catalog spanning
  ``easy`` + ``complex`` + ``optfn`` (so the missing-backend ``optfn`` path is exercised).
* **Tier 2 (``-m slow``)** — the real freshly-written ``results.json`` (skipped when no run
  exists), validated through the frozen contract via typed attribute access (no dict-key
  indexing — keeps the ``enforce-pydantic-native`` hook green).
"""

from __future__ import annotations

import math
from collections import Counter

import pytest

from oracles.cases import (
    CATEGORY_COUNTS,
    CATEGORY_REGISTRY,
    build_specs,
    materialize,
)
from oracles.bench_contract import BackendProfile, BenchReport, Featured
from oracles.engine import build_report
from oracles.reports import latest_results

SPECTRAFIT = "spectrafit"
LMFIT = "lmfit"
JAX = "jax"
OPTFN = "optfn"


# --------------------------------------------------------------------------- #
# Builders / fixtures
# --------------------------------------------------------------------------- #
def _mixed_catalog() -> list:
    """A small catalog spanning easy + complex + optfn (one optfn keeps DE cost low)."""
    specs = build_specs()
    picked = []
    for category, take in (("easy", 2), ("complex", 2), ("optfn", 1)):
        picked += [s for s in specs if s.category == category][:take]
    return [materialize(s) for s in picked]


@pytest.fixture(scope="module")
def tier1_report() -> BenchReport:
    """Fast report from a tiny injected catalog — the CI-default ground-truth check."""
    return build_report(n_reps=1, n_mc=2, catalog=_mixed_catalog(), ngrid=[128, 256])


@pytest.fixture(scope="module")
def tier2_report() -> BenchReport:
    """The real latest run, validated through the frozen contract; skip if none on disk."""
    path = latest_results("benchmark")
    if path is None:
        pytest.skip("no benchmark run on disk; run `uv run poe benchmark` first")
    return BenchReport.model_validate_json(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Helpers (no json.loads, no dict-key literals — pydantic-native friendly)
# --------------------------------------------------------------------------- #
def _freeze(value: object) -> object:
    """Hashable signature of a (possibly nested) numeric array for equality checks."""
    if isinstance(value, list):
        return tuple(_freeze(v) for v in value)
    return value


def _all_floats_finite(obj: object) -> bool:
    """True iff every float anywhere in a model_dump() tree is finite (no NaN/Inf)."""
    if isinstance(obj, bool):
        return True
    if isinstance(obj, float):
        return math.isfinite(obj)
    if isinstance(obj, dict):
        return all(_all_floats_finite(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return all(_all_floats_finite(v) for v in obj)
    return True


def _spectrafit(feat: Featured) -> BackendProfile:
    """The spectrafit profile of a case (present on every non-optfn case)."""
    return feat.profiles[SPECTRAFIT]


def _case_signature(feat: Featured) -> tuple:
    """A robust per-case identity over the data the plots draw.

    Combines the reference spectrum, the winner's cost history, and the correlation
    matrix so two genuinely-different cases never collide — even when one component is
    legitimately shared (e.g. an empty ``corr`` on optfn cases, or similar easy fits).
    """
    conv = _spectrafit(feat).conv if SPECTRAFIT in feat.profiles else []
    return (_freeze(feat.ref), _freeze(conv), _freeze(feat.corr))


def _first_of_category(report: BenchReport, category: str) -> Featured:
    """The first analyzed case of a category (assumes the category is deep-dived)."""
    return next(f for f in report.analyzed if f.category == category)


# --------------------------------------------------------------------------- #
# Tier 1 — fast, CI default
# --------------------------------------------------------------------------- #
def test_schema_round_trips(tier1_report: BenchReport) -> None:
    """The report serializes and re-validates losslessly through the camelCase contract."""
    raw = tier1_report.model_dump_json(by_alias=True)
    assert BenchReport.model_validate_json(raw).model_dump_json(by_alias=True) == raw


def test_categories_cover_the_registry(tier1_report: BenchReport) -> None:
    """Every registered category is advertised in the report's category list."""
    assert {c.id for c in tier1_report.categories} == set(CATEGORY_REGISTRY)


def test_analyzed_covers_suite_categories(tier1_report: BenchReport) -> None:
    """Every category present in the suite is ALSO deep-dived — the run_002 guard."""
    suite_cats = {c.category for c in tier1_report.suite}
    analyzed_cats = {f.category for f in tier1_report.analyzed}
    assert suite_cats <= analyzed_cats, (
        f"suite-only categories: {suite_cats - analyzed_cats}"
    )


def test_analyzed_is_multiple_and_unique(tier1_report: BenchReport) -> None:
    """More than one analyzed case, with unique ids — the single-case-mockup guard."""
    ids = [f.id for f in tier1_report.analyzed]
    assert len(ids) > 1
    assert len(set(ids)) == len(ids)


def test_analyzed_ids_exist_in_suite(tier1_report: BenchReport) -> None:
    """No orphan deep-dive: every analyzed id is also a suite row."""
    suite_ids = {c.id for c in tier1_report.suite}
    assert {f.id for f in tier1_report.analyzed} <= suite_ids


def test_optfn_backend_fairness(tier1_report: BenchReport) -> None:
    """optfn cases carry spectrafit + lmfit (DE oracle) but NOT jax (global unsupported)."""
    optfn_cases = [f for f in tier1_report.analyzed if f.category == OPTFN]
    assert optfn_cases, "tier-1 catalog must include an optfn case"
    for feat in optfn_cases:
        assert SPECTRAFIT in feat.profiles
        assert LMFIT in feat.profiles
        assert JAX not in feat.profiles


def test_correlation_matrices_are_square(tier1_report: BenchReport) -> None:
    """Each case's correlation matrix is square in its parameter count, or empty.

    ``optfn`` (landscape-recovery) cases legitimately carry an EMPTY ``corr`` —
    parameter correlation is meaningless for a multimodal surrogate fit — and the UI
    renders an explicit empty-state for it. Peak-fit cases must be square.
    """
    for feat in tier1_report.analyzed:
        assert len(feat.corr) in (0, len(feat.param_names))


def test_no_nonfinite_floats(tier1_report: BenchReport) -> None:
    """No NaN/Inf survives anywhere in the payload (sanitize + _finite end-to-end)."""
    assert _all_floats_finite(tier1_report.model_dump())


def test_plots_distinct_across_categories(tier1_report: BenchReport) -> None:
    """An easy vs a complex case have DIFFERENT plot arrays — the identical-plots guard.

    Compared across *different* categories (not two same-category cases) so genuinely
    similar siblings can't masquerade as a shared-fixture bug.
    """
    easy = _spectrafit(_first_of_category(tier1_report, "easy"))
    complx = _spectrafit(_first_of_category(tier1_report, "complex"))
    assert _freeze(easy.conv) != _freeze(complx.conv)
    assert _freeze(easy.grad) != _freeze(complx.grad)
    assert _freeze(_first_of_category(tier1_report, "easy").corr) != _freeze(
        _first_of_category(tier1_report, "complex").corr
    )


# --------------------------------------------------------------------------- #
# Tier 1.5 — fast real-run sentinel (CI default). The deep Tier-2 payload sweep
# below stays `-m slow` (one ~46 MB model_validate_json); this sentinel reads
# only the KB-sized manifest of the same run, so real-run drift (schema bump
# not re-run, catalog resize, gate key loss) is caught in every default run
# instead of only under `pytest -m slow`.
# --------------------------------------------------------------------------- #
def test_latest_run_manifest_sentinel() -> None:
    """Manifest of the real latest run must cohere with the current code."""
    import json

    from oracles.bench_contract import GATE_STATES, SCHEMA_VERSION, SUPPORTED_SCHEMA

    path = latest_results("benchmark")
    if path is None:
        pytest.skip("no benchmark run on disk; run `uv run poe benchmark` first")
    manifest_path = path.parent / "manifest.json"
    if not manifest_path.exists():
        pytest.skip(f"run {path.parent.name} has no manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Schema drift: an on-disk run older than the current window is stale.
    assert manifest["schema_version"] in SUPPORTED_SCHEMA, (
        f"latest run {manifest['run_id']} has schema {manifest['schema_version']} "
        f"outside the supported window {SUPPORTED_SCHEMA} — regenerate the benchmark"
    )
    if manifest["schema_version"] != SCHEMA_VERSION:
        # Old-but-migratable runs are tolerated; the roundtrip suite owns them.
        pytest.skip(
            f"latest run predates schema {SCHEMA_VERSION} — deep checks deferred"
        )

    # Catalog drift: the run must carry exactly the registry's case total.
    assert manifest["n_cases"] == sum(CATEGORY_COUNTS.values()), (
        f"run has {manifest['n_cases']} cases but the registry defines "
        f"{sum(CATEGORY_COUNTS.values())} — catalog changed since the run"
    )

    # Gate coherence: state present, valid, and numbers finite.
    assert manifest["gate_state"] in GATE_STATES
    assert math.isfinite(manifest["geomean_speedup_vs_baseline"])
    assert math.isfinite(manifest["max_abs_delta_r2"])

    # Backend roster: the subject and the baseline are both present.
    assert SPECTRAFIT in manifest["backends"]
    assert manifest["baseline_solver_id"] in manifest["backends"]


# --------------------------------------------------------------------------- #
# Tier 2 — slow, against the real latest run
# --------------------------------------------------------------------------- #
@pytest.mark.slow
def test_suite_counts_match_registry(tier2_report: BenchReport) -> None:
    """The real suite carries exactly the registry's per-category case counts."""
    counts = Counter(c.category for c in tier2_report.suite)
    assert dict(counts) == CATEGORY_COUNTS


@pytest.mark.slow
def test_full_catalog_is_deep_dived(tier2_report: BenchReport) -> None:
    """Every case is analyzed (139) and every category — incl. optfn — is represented."""
    assert len(tier2_report.analyzed) == sum(CATEGORY_COUNTS.values())
    analyzed_cats = {f.category for f in tier2_report.analyzed}
    assert set(CATEGORY_REGISTRY) <= analyzed_cats
    assert OPTFN in analyzed_cats


@pytest.mark.slow
def test_real_optfn_backend_fairness(tier2_report: BenchReport) -> None:
    """On the real run, every analyzed optfn case has spectrafit + lmfit, no jax."""
    optfn_cases = [f for f in tier2_report.analyzed if f.category == OPTFN]
    assert len(optfn_cases) == CATEGORY_COUNTS[OPTFN]
    for feat in optfn_cases:
        assert SPECTRAFIT in feat.profiles
        assert LMFIT in feat.profiles
        assert JAX not in feat.profiles


@pytest.mark.slow
def test_real_plots_distinct_for_all_adjacent_pairs(tier2_report: BenchReport) -> None:
    """No two consecutive analyzed cases share a plot signature — identical-plots guard at scale."""
    analyzed = tier2_report.analyzed
    for prev, cur in zip(analyzed, analyzed[1:]):
        assert _case_signature(prev) != _case_signature(cur), (
            f"identical plot data across {prev.id} and {cur.id}"
        )


@pytest.mark.slow
def test_real_no_nonfinite_floats(tier2_report: BenchReport) -> None:
    """The real serialized payload contains no NaN/Inf."""
    assert _all_floats_finite(tier2_report.model_dump())
