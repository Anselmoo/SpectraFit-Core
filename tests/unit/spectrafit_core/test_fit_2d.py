"""End-to-end 2-D fitting through ``spectrafit_core.fit`` (Gaussian2D).

Locks in the real 2-D path: the PyO3 boundary keeps ``len(x) == n_points * n_dims``
and reshapes to dims×points, and the solver builds ``x_concat`` point-major (stride
= n_dims) with point-count buffers sized by the residual count — so a planted 2-D
Gaussian is recovered. 1-D behaviour is unchanged (covered elsewhere).
"""

from __future__ import annotations

import numpy as np

from spectrafit_core.data import MeasurementData
from spectrafit_core.fit import fit
from spectrafit_core.graph import FitGraph
from spectrafit_core.models import ModelType
from spectrafit_core.parameters import Parameter

_TRUTH = {
    "amplitude": 5.0,
    "center_x": 0.5,
    "center_y": -1.0,
    "sigma_x": 1.2,
    "sigma_y": 0.8,
}


def _gaussian2d(coords: np.ndarray, p: dict[str, float]) -> np.ndarray:
    x, y = coords[:, 0], coords[:, 1]
    return p["amplitude"] * np.exp(
        -((x - p["center_x"]) ** 2) / (2 * p["sigma_x"] ** 2)
        - ((y - p["center_y"]) ** 2) / (2 * p["sigma_y"] ** 2)
    )


def _grid(n: int = 15, lo: float = -3.0, hi: float = 3.0) -> np.ndarray:
    gx = np.linspace(lo, hi, n)
    xx, yy = np.meshgrid(gx, gx)
    return np.column_stack([xx.ravel(), yy.ravel()])


def _graph() -> FitGraph:
    return FitGraph(
        nodes=[  # ty: ignore[invalid-argument-type]  # Pydantic coerces these dicts to ModelNodeSpec
            {
                "id": "g",
                "model_type": ModelType.GAUSSIAN2D,
                "parameters": {
                    "amplitude": Parameter(value=3.0),
                    "center_x": Parameter(value=0.0),
                    "center_y": Parameter(value=0.0),
                    "sigma_x": Parameter(value=1.0, min=1e-3),
                    "sigma_y": Parameter(value=1.0, min=1e-3),
                },
            }
        ]
    )


def test_gaussian2d_round_trip_recovers_params() -> None:
    """A Gaussian2D fit recovers the planted (a, cx, cy, sx, sy) from a far start."""
    coords = _grid()
    y = _gaussian2d(coords, _TRUTH)
    result = fit(_graph(), MeasurementData(x=coords.tolist(), y=y.tolist()))
    fitted = {k: v.value for k, v in result.parameters.items()}
    for name, truth in _TRUTH.items():
        assert abs(fitted[f"g.{name}"] - truth) < 1e-2, (
            name,
            fitted[f"g.{name}"],
            truth,
        )


def test_gaussian2d_best_fit_length_is_point_count() -> None:
    """best_fit has one entry per (x,y) point — not per coordinate component."""
    coords = _grid(n=12)
    y = _gaussian2d(coords, _TRUTH)
    result = fit(_graph(), MeasurementData(x=coords.tolist(), y=y.tolist()))
    assert len(result.best_fit) == coords.shape[0] == 144
