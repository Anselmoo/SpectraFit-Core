"""Phase 8 — test_models.py

Tests for Gaussian and Lorentzian model kernels evaluated at known points
via the _core extension module.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest

import spectrafit_core._core as _core


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _single_node_graph_json(node_id: str, model_type: str, params_spec: dict) -> str:
    """Build a minimal graph JSON with one node."""
    return json.dumps(
        {
            "schema_version": "0.1",
            "nodes": [
                {
                    "id": node_id,
                    "model_type": model_type,
                    "parameters": {
                        k: {
                            "value": v,
                            "min": None,
                            "max": None,
                            "vary": True,
                            "expr": None,
                            "scale": None,
                        }
                        for k, v in params_spec.items()
                    },
                }
            ],
            "expr_edges": [],
        }
    )


def _data_json(x_vals: list[float]) -> str:
    return json.dumps(
        {
            "schema_version": "0.1",
            "x": [[v] for v in x_vals],
            "y": [0.0] * len(x_vals),
            "sigma": None,
            "label": None,
        }
    )


def _params_json(node_id: str, params: dict[str, float]) -> str:
    return json.dumps({f"{node_id}.{k}": v for k, v in params.items()})


# ---------------------------------------------------------------------------
# Gaussian kernel tests
# ---------------------------------------------------------------------------


def test_gaussian_at_center_equals_amplitude() -> None:
    """Gaussian(x=center) == amplitude."""
    A, c, sigma = 4.5, 2.0, 0.8
    graph_j = _single_node_graph_json(
        "g", "gaussian", {"amplitude": A, "center": c, "sigma": sigma}
    )
    params_j = _params_json("g", {"amplitude": A, "center": c, "sigma": sigma})
    result = json.loads(_core.evaluate(graph_j, params_j, _data_json([c])))
    assert result[0] == pytest.approx(A, abs=1e-9)


def test_gaussian_falls_off_symmetrically() -> None:
    """Gaussian is symmetric: f(center - d) == f(center + d)."""
    A, c, sigma = 3.0, 1.0, 0.5
    d = 0.3
    graph_j = _single_node_graph_json(
        "g", "gaussian", {"amplitude": A, "center": c, "sigma": sigma}
    )
    params_j = _params_json("g", {"amplitude": A, "center": c, "sigma": sigma})
    result = json.loads(_core.evaluate(graph_j, params_j, _data_json([c - d, c + d])))
    assert result[0] == pytest.approx(result[1], abs=1e-12)


def test_gaussian_at_one_sigma_is_exp_neg_half() -> None:
    """Gaussian(x = center ± sigma) == amplitude * exp(-0.5)."""
    A, c, sigma = 2.0, 0.0, 1.0
    expected = A * math.exp(-0.5)
    graph_j = _single_node_graph_json(
        "g", "gaussian", {"amplitude": A, "center": c, "sigma": sigma}
    )
    params_j = _params_json("g", {"amplitude": A, "center": c, "sigma": sigma})
    result = json.loads(
        _core.evaluate(graph_j, params_j, _data_json([c + sigma, c - sigma]))
    )
    assert result[0] == pytest.approx(expected, abs=1e-9)
    assert result[1] == pytest.approx(expected, abs=1e-9)


def test_gaussian_amplitude_scales_linearly() -> None:
    """Doubling amplitude doubles the evaluated value."""
    c, sigma = 0.0, 1.0
    x_vals = [-0.5, 0.0, 0.5]
    for A in [1.0, 2.0]:
        graph_j = _single_node_graph_json(
            "g", "gaussian", {"amplitude": A, "center": c, "sigma": sigma}
        )
        params_j = _params_json("g", {"amplitude": A, "center": c, "sigma": sigma})
        result = json.loads(_core.evaluate(graph_j, params_j, _data_json(x_vals)))
        if A == 1.0:
            baseline = result.copy()
        else:
            for i, (b, r) in enumerate(zip(baseline, result)):
                assert r == pytest.approx(2 * b, abs=1e-12)


def test_gaussian_multiple_points() -> None:
    """Gaussian over multiple points matches analytical formula."""
    A, c, sigma = 5.0, 2.0, 0.5
    x_vals = np.linspace(0.0, 4.0, 20).tolist()
    expected = [A * math.exp(-0.5 * ((x - c) / sigma) ** 2) for x in x_vals]

    graph_j = _single_node_graph_json(
        "g", "gaussian", {"amplitude": A, "center": c, "sigma": sigma}
    )
    params_j = _params_json("g", {"amplitude": A, "center": c, "sigma": sigma})
    result = json.loads(_core.evaluate(graph_j, params_j, _data_json(x_vals)))

    np.testing.assert_allclose(result, expected, atol=1e-9)


# ---------------------------------------------------------------------------
# Lorentzian kernel tests
# ---------------------------------------------------------------------------


def test_lorentzian_at_center_equals_amplitude() -> None:
    """Lorentzian(x=center) == amplitude."""
    A, c, sigma = 3.0, -1.0, 0.5
    graph_j = _single_node_graph_json(
        "l", "lorentzian", {"amplitude": A, "center": c, "sigma": sigma}
    )
    params_j = _params_json("l", {"amplitude": A, "center": c, "sigma": sigma})
    result = json.loads(_core.evaluate(graph_j, params_j, _data_json([c])))
    assert result[0] == pytest.approx(A, abs=1e-9)


def test_lorentzian_falls_off_symmetrically() -> None:
    """Lorentzian is symmetric around center."""
    A, c, sigma = 2.0, 0.5, 0.8
    d = 0.4
    graph_j = _single_node_graph_json(
        "l", "lorentzian", {"amplitude": A, "center": c, "sigma": sigma}
    )
    params_j = _params_json("l", {"amplitude": A, "center": c, "sigma": sigma})
    result = json.loads(_core.evaluate(graph_j, params_j, _data_json([c - d, c + d])))
    assert result[0] == pytest.approx(result[1], abs=1e-12)


def test_lorentzian_at_half_width() -> None:
    """Lorentzian(x = center ± sigma) == amplitude * 0.5 (half maximum)."""
    A, c, sigma = 4.0, 0.0, 1.0
    expected = A * 0.5
    graph_j = _single_node_graph_json(
        "l", "lorentzian", {"amplitude": A, "center": c, "sigma": sigma}
    )
    params_j = _params_json("l", {"amplitude": A, "center": c, "sigma": sigma})
    result = json.loads(
        _core.evaluate(graph_j, params_j, _data_json([c + sigma, c - sigma]))
    )
    assert result[0] == pytest.approx(expected, abs=1e-9)
    assert result[1] == pytest.approx(expected, abs=1e-9)


def test_lorentzian_multiple_points() -> None:
    """Lorentzian over multiple points matches analytical formula."""
    A, c, sigma = 2.0, 0.0, 1.0
    x_vals = np.linspace(-3.0, 3.0, 15).tolist()
    # Lorentzian: A / (1 + ((x-c)/sigma)^2)
    expected = [A / (1.0 + ((x - c) / sigma) ** 2) for x in x_vals]

    graph_j = _single_node_graph_json(
        "l", "lorentzian", {"amplitude": A, "center": c, "sigma": sigma}
    )
    params_j = _params_json("l", {"amplitude": A, "center": c, "sigma": sigma})
    result = json.loads(_core.evaluate(graph_j, params_j, _data_json(x_vals)))

    np.testing.assert_allclose(result, expected, atol=1e-9)
