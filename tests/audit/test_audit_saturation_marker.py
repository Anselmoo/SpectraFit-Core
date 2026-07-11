"""Audit test: saturation markers in the latest manifest reflect the
raised-floor rule (EF-PY-09: _SATURATION_R2_FLOOR = 0.99).

A category is 'saturated' when EVERY case in it has:
  - inter-backend r² spread  ≤ 1e-3  (backends agree), AND
  - min(r²)                  ≥ 0.99  (agreement at a near-perfect fit, not mediocre)

Background: before EF-PY-09 the floor was 0.5, so a mediocre-but-unanimous
cluster (every backend equally wrong at r²≈0.5) was reported as "too easy /
solved".  After EF-PY-09 the floor is 0.99, which is a *real* fit-quality
ceiling.

Why 'easy' no longer saturates (changed with EF-PY-09):
  EZ-010 ("single lorentzian · faint #10") is a low-SNR case where the best
  achievable r² is ≈0.9886 — all five backends agree to within 1e-12, but
  min(r²) < 0.99, so the floor correctly excludes it.  Agreement at a
  noise-limited r² is not "solved / saturated"; the floor captures that.
  See python/benchmark/reports.py _SATURATION_R2_FLOOR.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from oracles.reports import REPORTS_ROOT, _SATURATION_INTERBACKEND_TOL, _SATURATION_R2_FLOOR

_FLOOR = _SATURATION_R2_FLOOR
_TOL = _SATURATION_INTERBACKEND_TOL


def _latest() -> Path | None:
    runs = sorted(REPORTS_ROOT.glob("benchmark/*/manifest.json"), reverse=True)
    return runs[0] if runs else None


def _results_for(manifest_path: Path) -> list[dict]:
    results_path = manifest_path.parent / "results.json"
    if not results_path.exists():
        return []
    return json.loads(results_path.read_text()).get("suite", [])


@pytest.mark.skipif(_latest() is None, reason="no run on disk")
def test_easy_no_longer_saturates_under_raised_floor() -> None:
    """'easy' is NOT saturated: EZ-010 (faint, low-SNR) has min r²≈0.9886 < 0.99 floor.

    The raised floor (EF-PY-09) is intentional — noise-limited agreement is not
    "solved".  This test documents the new reality and will catch any regression
    that silently re-admits 'easy' without all its cases genuinely meeting the floor.
    """
    path = _latest()
    assert path is not None
    manifest = json.loads(path.read_text())
    saturated = manifest.get("saturated_categories") or manifest.get("saturatedCategories") or []
    assert "easy" not in saturated, (
        f"manifest.saturated_categories = {saturated!r}; 'easy' should NOT be saturated "
        "under the 0.99 floor (EF-PY-09): EZ-010 (faint) has min r²≈0.9886 which is "
        "below the floor.  If 'easy' appears here, either the floor was lowered again "
        "or EZ-010 was replaced — check _SATURATION_R2_FLOOR and the easy suite."
    )


@pytest.mark.skipif(_latest() is None, reason="no run on disk")
def test_saturated_categories_are_non_empty_and_sound() -> None:
    """Every category in saturated_categories genuinely meets the raised-floor rule.

    Property-based: for each saturated category, ALL its cases must have
    min(r²) >= _SATURATION_R2_FLOOR and inter-backend spread <= _SATURATION_INTERBACKEND_TOL.
    Also asserts that at least one category saturates (non-vacuous).
    """
    path = _latest()
    assert path is not None
    manifest = json.loads(path.read_text())
    saturated = manifest.get("saturated_categories") or manifest.get("saturatedCategories") or []

    # Non-vacuous: some categories do saturate
    assert len(saturated) > 0, (
        "manifest.saturated_categories is empty — expected at least one category "
        "(e.g. 'reality', 'scaling', 'fixed', or 'tied') to meet the floor rule.  "
        "If the suite changed substantially this assertion may need updating."
    )

    suite = _results_for(path)
    if not suite:
        pytest.skip("results.json not found alongside manifest.json")

    # Build per-category per-case r2 maps
    by_cat: dict[str, list[dict]] = {}
    for case in suite:
        cat = case.get("category")
        if cat:
            by_cat.setdefault(cat, []).append(case)

    violations: list[str] = []
    for cat in saturated:
        cases = by_cat.get(cat, [])
        for c in cases:
            m = c.get("m") or {}
            r2s = []
            for solver_id, metric in m.items():
                r2 = metric.get("r2") if isinstance(metric, dict) else None
                if r2 is not None:
                    r2s.append(float(r2))
            if len(r2s) < 2:
                violations.append(
                    f"{cat}/{c.get('id')}: only {len(r2s)} backend(s) — "
                    "cannot establish inter-backend agreement"
                )
                continue
            min_r2 = min(r2s)
            spread = max(r2s) - min_r2
            if min_r2 < _FLOOR:
                violations.append(
                    f"{cat}/{c.get('id')}: min r²={min_r2:.6f} < floor {_FLOOR} "
                    "(floor rule violated)"
                )
            if spread > _TOL:
                violations.append(
                    f"{cat}/{c.get('id')}: spread={spread:.2e} > tol {_TOL} "
                    "(agreement rule violated)"
                )

    assert not violations, (
        "saturated_categories contains categories that violate the saturation rule:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
