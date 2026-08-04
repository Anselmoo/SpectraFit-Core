"""Category metadata invariants — one registry record, not N parallel maps.

Guards against silent drift between ``CATEGORY_REGISTRY`` (the single source of
truth) and the four backward-compatible derived dicts that engine.py / synth.py
import (``CATEGORY_COUNTS``, ``CATEGORY_LABELS``, ``PREFIX``, ``CATEGORY_HUE``).
"""

from __future__ import annotations

import collections

from oracles import cases, models


def test_registry_entries_are_well_formed() -> None:
    assert cases.CATEGORY_REGISTRY, "registry must not be empty"
    for cid, cdef in cases.CATEGORY_REGISTRY.items():
        assert cdef.id == cid, f"{cid}: registry key must equal CategoryDef.id"
        assert cdef.label.strip(), f"{cid}: label must be non-empty"
        assert cdef.prefix.strip(), f"{cid}: prefix must be non-empty"
        assert cdef.hue.strip(), f"{cid}: hue must be non-empty"
        assert cdef.count >= 0, f"{cid}: count must be non-negative"


def test_derived_dicts_share_the_registry_key_set() -> None:
    keys = set(cases.CATEGORY_REGISTRY)
    assert set(cases.CATEGORY_COUNTS) == keys
    assert set(cases.CATEGORY_LABELS) == keys
    assert set(cases.PREFIX) == keys
    assert set(cases.CATEGORY_HUE) == keys


def test_derived_dicts_carry_registry_values() -> None:
    for cid, cdef in cases.CATEGORY_REGISTRY.items():
        assert cases.CATEGORY_COUNTS[cid] == cdef.count
        assert cases.CATEGORY_LABELS[cid] == cdef.label
        assert cases.PREFIX[cid] == cdef.prefix
        assert cases.CATEGORY_HUE[cid] == cdef.hue


def test_build_catalog_totals_match_registry_counts() -> None:
    catalog = cases.build_catalog()
    counts = collections.Counter(b.category for b in catalog)
    assert dict(counts) == cases.CATEGORY_COUNTS
    assert len(catalog) == sum(cases.CATEGORY_COUNTS.values())


# --------------------------------------------------------------------------- #
# Anti-padding invariants: the catalog is diversity-driven, never N× repeats of
# the same shape (the "20× single gaussian" / "6 landscapes × 5" regression).
# --------------------------------------------------------------------------- #
def test_no_duplicate_model_condition_cases() -> None:
    """No two cases share (category, model-set, condition) — the core anti-padding rule."""
    catalog = cases.build_catalog()
    keys = [
        (c.category, frozenset(comp.model for comp in c.comp_true), c.spec.condition)
        for c in catalog
    ]
    dupes = [k for k, n in collections.Counter(keys).items() if n > 1]
    assert not dupes, f"redundant (category, models, condition) cases: {dupes}"


def test_every_case_has_a_condition_tag() -> None:
    """Every generated case carries a qualitative condition tag (no untagged padding)."""
    untagged = [c.id for c in cases.build_catalog() if not c.spec.condition]
    assert not untagged, f"cases without a condition tag: {untagged}"


def test_catalog_stays_lean() -> None:
    """A guardrail against silently re-padding the catalog back toward 360."""
    # Guard against re-padding toward the old 360; grows as genuinely-distinct kernels/
    # landscapes are added (diversity-driven, one case per model × condition).
    assert len(cases.build_catalog()) <= 170


def test_every_landscape_has_exactly_one_optfn_case() -> None:
    """optfn = one case per registered landscape (identical surrogate ⇒ no cycling)."""
    optfn = [c for c in cases.build_catalog() if c.category == "optfn"]
    seen = collections.Counter(c.spec.landscape for c in optfn)
    assert set(seen) == set(models.LANDSCAPE_REGISTRY)
    assert all(v == 1 for v in seen.values()), f"duplicated landscapes: {seen}"


def test_every_registered_peak_model_appears_in_a_case() -> None:
    """Each registered peak model (excluding pure backgrounds) is exercised by >=1 case."""
    used = {comp.model for c in cases.build_catalog() for comp in c.comp_true}
    registered = set(models.MODEL_REGISTRY) - {
        "constant",
        "linear",
        "quadratic",
        "tanh_step",
    }
    missing = registered - used
    assert not missing, f"registered models with no case: {sorted(missing)}"


def test_log_normal_cases_use_positive_x() -> None:
    """log-normal is only defined for x>0, so its cases must use a positive x-range."""
    for c in cases.build_catalog():
        if any(comp.model == "log_normal" for comp in c.comp_true):
            assert c.spec.x_min > 0.0, (
                f"{c.id}: log_normal case has x_min={c.spec.x_min} <= 0"
            )
