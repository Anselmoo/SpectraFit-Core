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
        raise ValueError("expected a 1-D array")
    # Input-boundary guard: NaN/inf must fail fast here, never reach the Rust
    # solver (where they silently produce NaN fits/covariance). Output finiteness
    # is already guarded in result.py; this is the symmetric input guard.
    if not np.isfinite(array).all():
        raise ValueError("values must be finite (no NaN/inf)")
    return array.astype(float).tolist()


def _as_coordinate_matrix(value: object) -> list[list[float]]:
    array = np.asarray(value, dtype=float)
    # Input-boundary guard (see _as_float_vector): reject NaN/inf coordinates.
    if not np.isfinite(array).all():
        raise ValueError("x values must be finite (no NaN/inf)")
    if array.ndim == 1:
        return [[float(item)] for item in array.tolist()]
    if array.ndim == 2:
        return [[float(item) for item in row] for row in array.tolist()]
    raise ValueError("x must have shape (N,) or (N, D)")


class MeasurementData(BaseModel):
    """One dataset to fit: coordinates ``x``, observations ``y``, and weights.

    Attributes:
        schema_version: IR schema version (do not change).
        x: Coordinate matrix of shape ``(N, D)``; 1-D input is promoted to
            ``(N, 1)``.
        y: Observed values, length ``N``.
        sigma: Optional per-point uncertainties, length ``N``; ``None`` weights
            every point equally.
        label: Optional human-readable dataset label.

    """

    schema_version: str = "0.1"
    # Accept either an (N, D) coordinate matrix or a flat (N,) vector; the
    # `_validate_x` before-validator promotes the 1-D form to (N, 1). The union
    # makes the constructor type match that accepted input (and what callers pass).
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
    def _validate_lengths(self) -> "MeasurementData":
        n_points = len(self.x)
        if len(self.y) != n_points:
            raise ValueError("x and y must have matching lengths")
        if self.sigma is not None and len(self.sigma) != n_points:
            raise ValueError("sigma must match x and y length")
        return self

    @property
    def n_points(self) -> int:
        """Return the number of data points in this dataset."""
        return len(self.y)


MeasurementInput = MeasurementData | Sequence[MeasurementData]
_MEASUREMENT_LIST_ADAPTER = TypeAdapter(list[MeasurementData])
_MEASUREMENT_SINGLE_ADAPTER = TypeAdapter(MeasurementData)


def dump_measurement_json(data: MeasurementInput) -> str:
    """Serialise one dataset or a sequence of datasets to a JSON string."""
    if isinstance(data, MeasurementData):
        return data.model_dump_json()
    datasets = [
        item
        if isinstance(item, MeasurementData)
        else MeasurementData.model_validate(item)
        for item in data
    ]
    return _MEASUREMENT_LIST_ADAPTER.dump_json(datasets).decode()


def normalize_measurement_input(
    data: MeasurementInput,
) -> MeasurementData | list[MeasurementData]:
    """Validate and coerce raw input into ``MeasurementData`` instance(s)."""
    if isinstance(data, MeasurementData):
        return _MEASUREMENT_SINGLE_ADAPTER.validate_python(data)
    return [
        item
        if isinstance(item, MeasurementData)
        else MeasurementData.model_validate(item)
        for item in data
    ]
