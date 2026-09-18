"""Measurement-data contracts and JSON helpers for the fitting boundary."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from pydantic import (
    BaseModel,
    ConfigDict,
    TypeAdapter,
    field_validator,
    model_validator,
)


def _as_float_vector(value: object) -> list[float]:
    array = np.asarray(value, dtype=float)
    if array.ndim != 1:
        msg = "expected a 1-D array"
        raise ValueError(msg)
    # Input-boundary guard: NaN/inf must fail fast here, never reach the Rust
    # solver (where they silently produce NaN fits/covariance). Output finiteness
    # is already guarded in result.py; this is the symmetric input guard.
    if not np.isfinite(array).all():
        msg = "values must be finite (no NaN/inf)"
        raise ValueError(msg)
    return array.astype(float).tolist()


def _as_coordinate_matrix(value: object) -> list[list[float]]:
    array = np.asarray(value, dtype=float)
    # Input-boundary guard (see _as_float_vector): reject NaN/inf coordinates.
    if not np.isfinite(array).all():
        msg = "x values must be finite (no NaN/inf)"
        raise ValueError(msg)
    if array.ndim == 1:
        return [[float(item)] for item in array.tolist()]
    if array.ndim == 2:
        return [[float(item) for item in row] for row in array.tolist()]
    msg = "x must have shape (N,) or (N, D)"
    raise ValueError(msg)


class MeasurementData(BaseModel):
    """One dataset to fit: coordinates ``x``, observations ``y``, and weights.

    Attributes:
        schema_version (str): IR schema version (do not change).
        x (list[list[float]] | list[float]): Independent coordinates on the
            wire as an ``(N, D)`` array: one row per data point, ``D``
            columns for a ``D``-dimensional fit (a plain length-``N`` list
            for 1-D). The ``_validate_x`` before-validator promotes flat 1-D
            input to ``(N, 1)``. The union keeps the constructor's declared
            type matching what callers actually pass.
        y (list[float]): Observed values, length ``N``.
        sigma (list[float] | None): Optional per-point uncertainties, length
            ``N``; ``None`` weights every point equally.
        label (str | None): Optional human-readable dataset label.

    """

    schema_version: str = "0.1"
    x: list[list[float]] | list[float]
    y: list[float]
    sigma: list[float] | None = None
    label: str | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("x", mode="before")
    @classmethod
    def _validate_x(cls, value: object) -> list[list[float]]:
        return _as_coordinate_matrix(value)

    @field_validator("y", "sigma", mode="before")
    @classmethod
    def _validate_vector(cls, value: object) -> list[float] | None:
        if value is None:
            return None
        return _as_float_vector(value)

    @model_validator(mode="after")
    def _validate_lengths(self) -> MeasurementData:
        n_points = len(self.x)
        if len(self.y) != n_points:
            msg = "x and y must have matching lengths"
            raise ValueError(msg)
        if self.sigma is not None and len(self.sigma) != n_points:
            msg = "sigma must match x and y length"
            raise ValueError(msg)
        return self

    @property
    def n_points(self) -> int:
        """Return the number of data points in this dataset."""
        return len(self.y)


MeasurementInput = MeasurementData | Sequence[MeasurementData]
_MEASUREMENT_LIST_ADAPTER = TypeAdapter(list[MeasurementData])
_MEASUREMENT_SINGLE_ADAPTER = TypeAdapter(MeasurementData)


def dump_measurement_json(data: MeasurementInput) -> str:
    """Serialise one dataset or a sequence of datasets to a JSON string.

    Args:
        data (MeasurementInput): A single [`MeasurementData`][spectrafit_core.MeasurementData]
            or a sequence of them; raw mapping-like items are validated into
            ``MeasurementData`` before serialisation.

    Returns:
        A JSON string: a single object for one dataset, or a JSON array of
        objects for a sequence.

    """
    if isinstance(data, MeasurementData):
        return data.model_dump_json()
    datasets = [
        item if isinstance(item, MeasurementData) else MeasurementData.model_validate(item)
        for item in data
    ]
    return _MEASUREMENT_LIST_ADAPTER.dump_json(datasets).decode()


def normalize_measurement_input(
    data: MeasurementInput,
) -> MeasurementData | list[MeasurementData]:
    """Validate and coerce raw input into ``MeasurementData`` instance(s).

    Args:
        data (MeasurementInput): A single [`MeasurementData`][spectrafit_core.MeasurementData]
            (or anything ``MeasurementData.model_validate`` accepts), or a
            sequence of such items.

    Returns:
        A single validated ``MeasurementData`` when ``data`` was a single
        dataset, otherwise a list of validated ``MeasurementData`` in the
        same order as ``data``.

    """
    if isinstance(data, MeasurementData):
        return _MEASUREMENT_SINGLE_ADAPTER.validate_python(data)
    return [
        item if isinstance(item, MeasurementData) else MeasurementData.model_validate(item)
        for item in data
    ]
