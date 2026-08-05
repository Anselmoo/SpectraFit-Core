"""Ground-truth recovery V&V for the 2-D map and global-fit showcases.

The engine plants known truth inside ``_multidim`` (two 2-D Gaussians,
noise σ=0.08, rng seed 7) and ``_global_fit`` (two 1-D Gaussian peaks with
exponential kinetics across a dataset axis, noise σ=0.04, rng seed 11), then
*fits* it with the real spectrafit subject. The pre-existing tests only asserted
the payloads exist (shape-only); these tests close the V&V gap by asserting the
**displayed fitted parameters recover the engine's own planted truth**.

Both engine functions are deterministic — the rng seeds are fixed inside the
functions — so the tolerances below are tight but not flaky:

- 2-D peaks: worst observed relative error is +1.0% (peak1 amplitude
  3.5349 vs 3.5); 5% rel covers every (a, cx, cy, sx, sy) with huge margin.
- Global fit: shared centers recover within 0.03% (2% asserted), shared
  sigmas within 0.36% (5% asserted), and every per-slice amplitude tracks the
  planted kinetics within 0.46% of the trace maximum (10% asserted).
"""

from __future__ import annotations

import numpy as np
import pytest

pytest.importorskip("lmfit")
pytest.importorskip("spectrafit_core")

from oracles.engine import _global_fit, _multidim

# Planted truth in `_multidim` (engine.py): one 3-D Gaussian (SP-2 N-D showcase),
# amplitude + per-axis center/sigma, fit with the parametric gaussian_nd kernel.
_MULTIDIM_TRUTH_AMP = 6.0
_MULTIDIM_TRUTH_CENTER = (-1.5, 1.0, 0.5)
_MULTIDIM_TRUTH_SIGMA = (1.6, 2.1, 1.2)

# Planted truth in `_global_fit` (engine.py).
_GF_CENTERS = (-1.8, 2.0)
_GF_SIGMAS = (0.9, 1.1)


def test_multidim_recovers_planted_truth() -> None:
    """Wire: _multidim's displayed N-D peak must recover its own planted 3-D truth."""
    md = _multidim()

    assert md.source == "spectrafit-core"
    assert md.n_dims == 3
    assert md.shape == [14, 14, 14]
    assert md.n_points == 14**3
    assert len(md.peaks) == 1

    pk = md.peaks[0]
    assert abs(pk.amplitude - _MULTIDIM_TRUTH_AMP) / _MULTIDIM_TRUTH_AMP < 0.05
    assert len(pk.center) == len(pk.sigma) == 3
    for i in range(3):
        rel_c = abs(pk.center[i] - _MULTIDIM_TRUTH_CENTER[i]) / abs(
            _MULTIDIM_TRUTH_CENTER[i]
        )
        rel_s = abs(pk.sigma[i] - _MULTIDIM_TRUTH_SIGMA[i]) / _MULTIDIM_TRUTH_SIGMA[i]
        assert rel_c < 0.05, (i, pk.center[i], _MULTIDIM_TRUTH_CENTER[i])
        assert rel_s < 0.05, (i, pk.sigma[i], _MULTIDIM_TRUTH_SIGMA[i])

    # A genuine recovery: r² is near-perfect on the noise-dominated synthetic fit.
    assert md.r_squared > 0.99, f"poor 3-D recovery: r²={md.r_squared}"


def test_global_fit_recovers_planted_kinetics() -> None:
    """Wire: the joint global fit must recover the planted shared shape + amplitude traces."""
    gf = _global_fit()

    assert gf.source == "spectrafit-core"
    assert len(gf.traces) == 2

    dataset_axis = np.asarray(gf.dataset_axis, dtype=float)
    # Planted amplitude traces (engine.py): peak A decays, peak B rises along the axis.
    truth_amp = (
        5.0 * np.exp(-dataset_axis / 4.0),
        4.0 * (1.0 - np.exp(-dataset_axis / 3.0)),
    )

    for k, trace in enumerate(gf.traces):
        # Shared (global) shape parameters across all 12 slices.
        rel_c = abs(trace.center - _GF_CENTERS[k]) / abs(_GF_CENTERS[k])
        assert rel_c < 0.02, (
            f"trace {k} center {trace.center} vs planted {_GF_CENTERS[k]} "
            f"(rel {rel_c:.4f})"
        )
        rel_s = abs(trace.sigma - _GF_SIGMAS[k]) / _GF_SIGMAS[k]
        assert rel_s < 0.05, (
            f"trace {k} sigma {trace.sigma} vs planted {_GF_SIGMAS[k]} "
            f"(rel {rel_s:.4f})"
        )

        # Per-slice amplitudes must track the planted trace curve.
        amp = np.asarray(trace.amplitude, dtype=float)
        assert amp.shape == dataset_axis.shape
        err = np.abs(amp - truth_amp[k]) / truth_amp[k].max()
        assert err.max() < 0.1, (
            f"trace {k} amplitude trace departs from planted kinetics: "
            f"max normalized error {err.max():.4f} at coord={dataset_axis[err.argmax()]}"
        )
