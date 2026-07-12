"""End-to-end N-D (≥3-D) fitting through ``spectrafit_core.fit`` (gaussian_nd).

Locks in the real N-D path (SP-2): the Python guard no longer rejects ``n_dims > 2``,
``ModelType.GAUSSIAN_ND`` is accepted, and the Rust compiler infers the model's
dimensionality from the node's indexed ``center_<i>`` parameters. A planted 3-D
Gaussian is recovered end-to-end. Higher-D coverage (5-D) lives in the Rust solver
tests; here we prove the Python boundary opens past 2-D.
"""

from __future__ import annotations

import numpy as np

from spectrafit_core.data import MeasurementData
from spectrafit_core.fit import fit
from spectrafit_core.graph import FitGraph
from spectrafit_core.models import ModelType
from spectrafit_core.parameters import Parameter

_TRUTH = {
    "amplitude": 4.0,
    "center_0": -1.0,
    "center_1": 0.5,
    "center_2": 1.2,
    "sigma_0": 1.1,
    "sigma_1": 0.9,
    "sigma_2": 1.3,
}


def _gaussian3d(coords: np.ndarray, p: dict[str, float]) -> np.ndarray:
    x, y, z = coords[:, 0], coords[:, 1], coords[:, 2]
    return p["amplitude"] * np.exp(
        -((x - p["center_0"]) ** 2) / (2 * p["sigma_0"] ** 2)
        - ((y - p["center_1"]) ** 2) / (2 * p["sigma_1"] ** 2)
        - ((z - p["center_2"]) ** 2) / (2 * p["sigma_2"] ** 2)
    )


def _grid(n: int = 8, lo: float = -3.0, hi: float = 3.0) -> np.ndarray:
    g = np.linspace(lo, hi, n)
    xx, yy, zz = np.meshgrid(g, g, g)
    return np.column_stack([xx.ravel(), yy.ravel(), zz.ravel()])


def _graph() -> FitGraph:
    return FitGraph(
        nodes=[  # ty: ignore[invalid-argument-type]  # Pydantic coerces these dicts to ModelNodeSpec
            {
                "id": "g",
                "model_type": ModelType.GAUSSIAN_ND,
                "parameters": {
                    "amplitude": Parameter(value=2.0),
                    "center_0": Parameter(value=-0.5),
                    "center_1": Parameter(value=0.0),
                    "center_2": Parameter(value=0.8),
                    "sigma_0": Parameter(value=1.0, min=1e-3),
                    "sigma_1": Parameter(value=1.0, min=1e-3),
                    "sigma_2": Parameter(value=1.0, min=1e-3),
                },
            }
        ]
    )


def test_gaussian_nd_3d_round_trip_recovers_params() -> None:
    """A 3-D gaussian_nd fit recovers the planted params from a far start.

    The Python ``n_dims > 2`` guard is gone (SP-2) and the Rust compiler infers
    D=3 from the node's ``center_0/center_1/center_2`` parameters.
    """
    coords = _grid()
    y = _gaussian3d(coords, _TRUTH)
    result = fit(_graph(), MeasurementData(x=coords.tolist(), y=y.tolist()))
    assert result.success
    fitted = {k: v.value for k, v in result.parameters.items()}
    for name, truth in _TRUTH.items():
        assert abs(fitted[f"g.{name}"] - truth) < 1e-2, (
            name,
            fitted[f"g.{name}"],
            truth,
        )


def test_gaussian_nd_best_fit_length_is_point_count() -> None:
    """best_fit has one entry per 3-D point — not per coordinate component."""
    coords = _grid(n=6)
    y = _gaussian3d(coords, _TRUTH)
    result = fit(_graph(), MeasurementData(x=coords.tolist(), y=y.tolist()))
    assert len(result.best_fit) == coords.shape[0] == 216
