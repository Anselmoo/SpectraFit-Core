"""Tests for MeasurementData and the JSON helpers in spectrafit_core.data.

Pins the module's public contract: coordinate promotion (1-D -> (N, 1)),
dtype coercion to float, the input-boundary finiteness guard (NaN/inf must
fail fast before reaching the Rust solver), length cross-validation,
extra-field rejection, and the dump/normalize helper pair. Characterization
tests only — current behavior is pinned, not idealized.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from pydantic import ValidationError

from spectrafit_core.data import (
    MeasurementData,
    dump_measurement_json,
    normalize_measurement_input,
)

# ---------------------------------------------------------------------------
# MeasurementData — construction and coercion
# ---------------------------------------------------------------------------


def test_minimal_construction_promotes_1d_x() -> None:
    data = MeasurementData(x=[1.0, 2.0, 3.0], y=[10.0, 20.0, 30.0])
    assert data.schema_version == "0.1"
    assert data.x == [[1.0], [2.0], [3.0]]
    assert data.y == [10.0, 20.0, 30.0]
    assert data.sigma is None
    assert data.label is None


def test_2d_x_is_preserved_row_wise() -> None:
    data = MeasurementData(
        x=[[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]],
        y=[0.0, 1.0, 2.0],
    )
    assert data.x == [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]
    assert data.n_points == 3


def test_numpy_inputs_are_coerced_to_plain_floats() -> None:
    data = MeasurementData(
        x=np.arange(4),  # ty: ignore[invalid-argument-type]  # before-validator coerces ndarray
        y=np.array([1, 2, 3, 4], dtype=np.int64),  # ty: ignore[invalid-argument-type]
        sigma=np.full(4, 0.5, dtype=np.float32),  # ty: ignore[invalid-argument-type]
    )
    assert data.x == [[0.0], [1.0], [2.0], [3.0]]
    assert data.y == [1.0, 2.0, 3.0, 4.0]
    assert data.sigma == [0.5, 0.5, 0.5, 0.5]
    assert all(isinstance(v, float) for v in data.y)


def test_numeric_strings_are_coerced_via_numpy() -> None:
    data = MeasurementData(x=["1.0", "2.5"], y=["3.0", "4.5"])  # ty: ignore[invalid-argument-type]  # before-validator coerces numeric strings
    assert data.x == [[1.0], [2.5]]
    assert data.y == [3.0, 4.5]


def test_empty_dataset_is_accepted() -> None:
    data = MeasurementData(x=[], y=[])
    assert data.x == []
    assert data.y == []
    assert data.n_points == 0


def test_sigma_and_label_round_through() -> None:
    data = MeasurementData(
        x=[1.0, 2.0],
        y=[3.0, 4.0],
        sigma=[0.1, 0.2],
        label="scan-1",
    )
    assert data.sigma == [0.1, 0.2]
    assert data.label == "scan-1"


def test_n_points_matches_y_length() -> None:
    data = MeasurementData(x=[[1.0, 9.0], [2.0, 8.0]], y=[5.0, 6.0])
    assert data.n_points == 2
    assert data.n_points == len(data.y)


# ---------------------------------------------------------------------------
# MeasurementData — validation failures
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_y_is_rejected(bad: float) -> None:
    with pytest.raises(ValidationError, match="finite"):
        MeasurementData(x=[1.0, 2.0], y=[1.0, bad])


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_x_is_rejected(bad: float) -> None:
    with pytest.raises(ValidationError, match="finite"):
        MeasurementData(x=[1.0, bad], y=[1.0, 2.0])


def test_non_finite_sigma_is_rejected() -> None:
    with pytest.raises(ValidationError, match="finite"):
        MeasurementData(x=[1.0], y=[1.0], sigma=[float("nan")])


def test_scalar_x_is_rejected() -> None:
    with pytest.raises(ValidationError, match=r"shape \(N,\) or \(N, D\)"):
        MeasurementData(x=5.0, y=[1.0])  # ty: ignore[invalid-argument-type]  # scalar deliberately invalid


def test_3d_x_is_rejected() -> None:
    with pytest.raises(ValidationError, match=r"shape \(N,\) or \(N, D\)"):
        MeasurementData(x=np.zeros((2, 2, 2)), y=[1.0, 2.0])  # ty: ignore[invalid-argument-type]  # 3-D deliberately invalid


def test_2d_y_is_rejected() -> None:
    with pytest.raises(ValidationError, match="1-D"):
        MeasurementData(x=[1.0, 2.0], y=[[1.0, 2.0]])  # ty: ignore[invalid-argument-type]  # 2-D y deliberately invalid


def test_x_y_length_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError, match="matching lengths"):
        MeasurementData(x=[1.0, 2.0, 3.0], y=[1.0, 2.0])


def test_sigma_length_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError, match="sigma must match"):
        MeasurementData(x=[1.0, 2.0], y=[1.0, 2.0], sigma=[0.1])


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        MeasurementData(x=[1.0], y=[1.0], weights=[1.0])  # type: ignore[call-arg]  # ty: ignore[unknown-argument]


def test_model_dump_round_trip() -> None:
    original = MeasurementData(x=[1.0, 2.0], y=[3.0, 4.0], sigma=[0.1, 0.2])
    restored = MeasurementData.model_validate(original.model_dump())
    assert restored == original


# ---------------------------------------------------------------------------
# dump_measurement_json
# ---------------------------------------------------------------------------


def test_dump_single_dataset_emits_json_object() -> None:
    data = MeasurementData(x=[1.0, 2.0], y=[3.0, 4.0], label="a")
    payload = json.loads(dump_measurement_json(data))
    assert payload["x"] == [[1.0], [2.0]]
    assert payload["y"] == [3.0, 4.0]
    assert payload["sigma"] is None
    assert payload["label"] == "a"
    assert payload["schema_version"] == "0.1"


def test_dump_sequence_emits_json_array() -> None:
    datasets = [
        MeasurementData(x=[1.0], y=[2.0]),
        MeasurementData(x=[3.0], y=[4.0]),
    ]
    payload = json.loads(dump_measurement_json(datasets))
    assert isinstance(payload, list)
    assert [item["y"] for item in payload] == [[2.0], [4.0]]


def test_dump_sequence_coerces_raw_dict_items() -> None:
    payload = json.loads(
        dump_measurement_json([{"x": [1.0, 2.0], "y": [3.0, 4.0]}]),  # type: ignore[list-item]  # ty: ignore[invalid-argument-type]
    )
    assert payload == [
        {
            "schema_version": "0.1",
            "x": [[1.0], [2.0]],
            "y": [3.0, 4.0],
            "sigma": None,
            "label": None,
        },
    ]


def test_dump_empty_sequence_emits_empty_array() -> None:
    assert json.loads(dump_measurement_json([])) == []


def test_dump_invalid_dict_item_raises() -> None:
    with pytest.raises(ValidationError):
        dump_measurement_json([{"x": [1.0], "y": [1.0, 2.0]}])  # type: ignore[list-item]  # ty: ignore[invalid-argument-type]


# ---------------------------------------------------------------------------
# normalize_measurement_input
# ---------------------------------------------------------------------------


def test_normalize_single_instance_returns_equal_instance() -> None:
    data = MeasurementData(x=[1.0], y=[2.0])
    result = normalize_measurement_input(data)
    assert isinstance(result, MeasurementData)
    assert result == data


def test_normalize_sequence_of_instances_returns_list() -> None:
    datasets = [
        MeasurementData(x=[1.0], y=[2.0]),
        MeasurementData(x=[3.0], y=[4.0]),
    ]
    result = normalize_measurement_input(datasets)
    assert result == datasets
    assert isinstance(result, list)


def test_normalize_sequence_coerces_raw_dict_items() -> None:
    result = normalize_measurement_input(
        [{"x": [1.0, 2.0], "y": [3.0, 4.0]}],  # type: ignore[list-item]  # ty: ignore[invalid-argument-type]
    )
    assert isinstance(result, list)
    assert len(result) == 1
    assert isinstance(result[0], MeasurementData)
    assert result[0].x == [[1.0], [2.0]]


def test_normalize_mixed_sequence_preserves_order() -> None:
    instance = MeasurementData(x=[1.0], y=[2.0])
    result = normalize_measurement_input(
        [instance, {"x": [3.0], "y": [4.0]}],  # type: ignore[list-item]  # ty: ignore[invalid-argument-type]
    )
    assert isinstance(result, list)
    assert result[0] == instance
    assert result[1].y == [4.0]


def test_normalize_empty_sequence_returns_empty_list() -> None:
    assert normalize_measurement_input([]) == []


def test_normalize_invalid_dict_item_raises() -> None:
    with pytest.raises(ValidationError):
        normalize_measurement_input(
            [{"x": [1.0], "y": [float("nan")]}],  # type: ignore[list-item]  # ty: ignore[invalid-argument-type]
        )
