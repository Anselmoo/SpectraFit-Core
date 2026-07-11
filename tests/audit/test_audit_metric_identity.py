"""Wire W2a — r²/RMSE must equal the value recomputed from the stored curves.

Catches: stale-cache bugs, aggregation bugs, mixing per-case vs per-backend.

The curves live on ``analyzed[]`` (``Featured``): each case carries ``x`` and,
per backend, ``profiles[b].fit.curve`` (the model curve) + ``fit.resid`` (the
residual ``y − curve``), so the observed data is ``y = curve + resid``. The
reported scalar is ``profiles[b].summary.r2`` (and ``.rmse``).

Faithfulness caveat (the kernel of G26): for large-N ``scaling`` cases the
stored ``x``/``curve``/``resid`` are **decimated** to a plotting cap (e.g.
600 → 200 points) while ``summary.r2`` is computed on the FULL data, so
recomputation from the stored subsample is only approximate there. The exact
identity is therefore asserted only on **full-resolution** records — detected
by ``len(stored x) == CaseSpec.n_points`` — which is the majority (≈123 of 151
cases). Storing the full arrays for every case would just balloon the ~50 MB
``results.json`` (the reason they are decimated in the first place), so this
wire is closed against the faithful records rather than by widening the
contract.

Note (2026-07-03, G26): the earlier version probed ``suite[]`` for raw
``(x, y, fit)`` arrays that the compact suite table has never carried, so it
always hit ``probed == 0`` and skipped ("extend engine.py first"). The curves
already exist on ``analyzed[]``; the wire is closed against them here.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
import pytest

from oracles.cases import build_specs
from oracles.metrics import chi2_red_of, r2_of, rmse_of
from oracles.reports import REPORTS_ROOT

# Minimum number of verifiable records when a run exists on disk. A regression
# that dropped the stored curves would make the probe loop find nothing;
# asserting a floor turns that into a loud failure instead of a silent skip.
_MIN_PROBES = 50
_MIN_SUITE_PROBES = 10


def _latest_results_path() -> Path | None:
    candidates = sorted(REPORTS_ROOT.glob("benchmark/*/results.json"), reverse=True)
    return candidates[0] if candidates else None


def _load_latest() -> dict:
    path = _latest_results_path()
    assert path is not None  # narrowed for static analysis; skipif guards runtime
    return json.loads(path.read_text())


def _spec_n_points() -> dict[str, int]:
    """Full-resolution point count per case id (before any plotting decimation)."""
    return {s.id: s.n_points for s in build_specs()}


def _faithful_records(payload: dict) -> Iterator[tuple[str, str, np.ndarray, np.ndarray, dict]]:
    """Yield (case_id, backend_id, y, curve, summary) for full-resolution records only.

    ``y`` is reconstructed as ``curve + resid``; decimated (large-N) cases whose
    stored curve is shorter than their materialized ``n_points`` are skipped —
    their stored arrays cannot reproduce the full-data metric exactly.
    """
    n_points = _spec_n_points()
    for feat in payload.get("analyzed") or []:
        cid = feat.get("id")
        x = feat.get("x")
        if cid is None or x is None or len(x) != n_points.get(cid):
            continue
        for backend_id, profile in (feat.get("profiles") or {}).items():
            fit = profile.get("fit") or {}
            curve = fit.get("curve")
            resid = fit.get("resid")
            summary = profile.get("summary") or {}
            if curve is None or resid is None:
                continue
            curve_arr = np.asarray(curve, dtype=float)
            y = curve_arr + np.asarray(resid, dtype=float)
            yield cid, backend_id, y, curve_arr, summary


def _assert_metric_identity(
    field: str, oracle: Callable[[np.ndarray, np.ndarray], float]
) -> None:
    payload = _load_latest()
    probed = 0
    for cid, backend_id, y, curve, summary in _faithful_records(payload):
        reported = summary.get(field)
        if reported is None:
            continue
        recomputed = oracle(y, curve)
        assert recomputed == pytest.approx(reported, abs=1e-8), (
            f"{field} drift on case={cid!r} backend={backend_id!r}: "
            f"reported={reported} recomputed={recomputed}"
        )
        probed += 1
    assert probed >= _MIN_PROBES, (
        f"only {probed} full-resolution records carried curve+resid+{field}; "
        f"expected ≥ {_MIN_PROBES} — the featured curves regressed"
    )


@pytest.mark.skipif(_latest_results_path() is None, reason="no benchmark run on disk yet")
def test_r2_recomputed_matches_featured_summary() -> None:
    """summary.r2 == r2_of(curve + resid, curve) on every full-resolution record."""
    _assert_metric_identity("r2", r2_of)


@pytest.mark.skipif(_latest_results_path() is None, reason="no benchmark run on disk yet")
def test_rmse_recomputed_matches_featured_summary() -> None:
    """summary.rmse == rmse_of(curve + resid, curve) on every full-resolution record."""
    _assert_metric_identity("rmse", rmse_of)


@pytest.mark.skipif(_latest_results_path() is None, reason="no benchmark run on disk yet")
def test_suite_scalar_r2_matches_featured_summary() -> None:
    """The compact suite[] scalar r2 must equal the featured summary it summarizes.

    This is the "mixing per-case vs per-backend" aggregation guard: a drift means
    suite[] and analyzed[] were populated from different fits (a real indexing
    bug). Restricted to the subject ``spectrafit``: suite[] (``run_suite``) and
    analyzed[] (``run_featured``) are TWO independent fit passes run at different
    ``n_reps``, so an equal-r² assertion is only sound for a deterministic
    backend. spectrafit's faer LM + seeded DE are deterministic (identical
    result at any n_reps), so its r² must match bit-for-bit; the oracle backends
    are not asserted here to avoid coupling to their reproducibility. Decimation
    does not affect this check — both sides carry the same reported scalar.
    """
    payload = _load_latest()
    summary_r2: dict[str, float] = {}
    for feat in payload.get("analyzed") or []:
        cid = feat.get("id")
        prof = (feat.get("profiles") or {}).get("spectrafit") or {}
        r2 = (prof.get("summary") or {}).get("r2")
        if cid is not None and r2 is not None:
            summary_r2[cid] = r2

    probed = 0
    for case in payload.get("suite") or []:
        cid = case.get("id")
        metric = (case.get("m") or {}).get("spectrafit") or {}
        suite_r2 = metric.get("r2")
        if cid not in summary_r2 or suite_r2 is None:
            continue
        assert suite_r2 == pytest.approx(summary_r2[cid], abs=1e-8), (
            f"suite/analyzed spectrafit r² mismatch on case={cid!r}: "
            f"suite={suite_r2} featured={summary_r2[cid]}"
        )
        probed += 1
    assert probed >= _MIN_SUITE_PROBES, (
        f"only {probed} (case, backend) records were present in both suite[] and "
        f"analyzed[]; expected ≥ {_MIN_SUITE_PROBES}"
    )


def test_metric_oracles_are_importable_and_callable() -> None:
    """The recomputation oracles exist and behave (guard against import drift)."""
    y = np.array([1.0, 2.0, 3.0])
    fit = np.array([1.1, 1.9, 3.1])

    rmse = rmse_of(y, fit)
    assert isinstance(rmse, float)
    assert rmse > 0, "rmse should be positive for different y and fit"

    chi2 = chi2_red_of(y, fit, None, dof=1)
    assert isinstance(chi2, float)
    assert chi2 > 0, "chi2_red should be positive for different y and fit"
