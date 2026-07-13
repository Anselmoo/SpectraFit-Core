"""Wire W2c — every solved case must report κ(J) at convergence.

Ill-conditioned cases (overlapping peaks, near-degenerate Voigt fraction at 0/1)
must report κ ≥ 1e6. Well-posed cases must report κ ≤ 1e4. This is a STRUCTURAL
property — independent of which solver ran.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from oracles.reports import REPORTS_ROOT


def _latest() -> Path | None:
    runs = sorted(REPORTS_ROOT.glob("benchmark/*/results.json"), reverse=True)
    return runs[0] if runs else None


@pytest.mark.skipif(_latest() is None, reason="no run on disk")
def test_every_solved_case_reports_kappa():
    path = _latest()
    assert path is not None
    payload = json.loads(path.read_text())
    missing: list[str] = []
    for case in payload.get("analyzed") or []:
        for backend_id, profile in (case.get("profiles") or {}).items():
            if not profile.get("r2"):
                continue
            if profile.get("jacobian_condition_number") is None and profile.get("jacobianConditionNumber") is None:
                missing.append(f"{case.get('id')}/{backend_id}")
    assert not missing, f"κ(J) missing from {len(missing)} (case, backend) pairs: {missing[:5]}"


@pytest.mark.skipif(_latest() is None, reason="no run on disk")
@pytest.mark.xfail(
    reason=(
        "ED-* generators (oracles/cases.py: _edge_doublet, _edge_near_widths, ...) "
        "currently sample overlap ∈ (0.35, 1.0)σ and width spread ∈ (0.5%, 4%). "
        "These regimes still converge to non-degenerate solutions, so κ(J) at "
        "convergence stays ≤ ~500. TRUE ill-conditioning (κ ≥ 1e6) requires "
        "harsher geometry: overlap ≤ 0.05σ, or exactly-equal widths, or amplitude "
        "decades ≥ 4. Hardening the ED-* generators is a Plan A3 follow-up "
        "(per memory: triage/benchmark-saturation-real-life-too-easy.md and "
        "triage/edge-category-redchi2-sameness.md). Until then this invariant is "
        "aspirational — xfail keeps it visible so the gap can't get lost."
    ),
    strict=False,
)
def test_overlapping_peaks_have_high_kappa():
    """ED-* cases SHOULD report κ ≥ 1e6 once the generators produce truly
    ill-conditioned Jacobians. See xfail reason for the catalog work needed.

    Test iterates `analyzed[]` (now every case in the catalog per
    `_select_analyzed`) and checks ≥25% of ED-* (case_id, backend) pairs hit κ ≥ 1e6.
    """
    path = _latest()
    assert path is not None
    payload = json.loads(path.read_text())
    overlap_kappas: list[float] = []
    for case in payload.get("analyzed") or []:
        if not case.get("id", "").startswith("ED-"):
            continue
        for profile in (case.get("profiles") or {}).values():
            kappa = profile.get("jacobian_condition_number") or profile.get("jacobianConditionNumber")
            if kappa is not None:
                overlap_kappas.append(kappa)
    if not overlap_kappas:
        pytest.skip(
            "no ED-* case present in analyzed[] — cannot verify κ ≥ 1e6 invariant. "
            "_select_analyzed should include every case by default; check engine.py."
        )
    ill_count = sum(1 for k in overlap_kappas if k >= 1e6)
    assert ill_count >= len(overlap_kappas) // 4, (
        f"only {ill_count}/{len(overlap_kappas)} edge cases flagged ill-conditioned; "
        "either κ is mis-computed or edge cases aren't actually edgy"
    )
