"""Tests for FitOptions — the Pydantic solver-configuration contract.

Covers default construction, explicit valid construction, per-field boundary
validation (ge/gt/lt constraints), extra-field rejection, and model_dump /
model_validate round-trip.  All tests are fast (<1 ms each); no solver calls
or numpy required.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from spectrafit_core.options import FitOptions


def test_defaults_construct_cleanly() -> None:
    opts = FitOptions()
    assert opts.schema_version == "0.1"
    assert opts.solver == "lm"
    assert opts.max_iterations == 200
    assert opts.tolerance == pytest.approx(1e-8)
    assert opts.delta0 is None
    assert opts.max_delta is None
    assert opts.eta is None
    assert opts.jacobian == "analytic"


def test_valid_explicit_construction() -> None:
    opts = FitOptions(
        schema_version="0.1",
        solver="trf",
        max_iterations=500,
        tolerance=1e-6,
        delta0=0.5,
        max_delta=10.0,
        eta=0.1,
    )
    assert opts.solver == "trf"
    assert opts.max_iterations == 500
    assert opts.tolerance == pytest.approx(1e-6)
    assert opts.delta0 == pytest.approx(0.5)
    assert opts.max_delta == pytest.approx(10.0)
    assert opts.eta == pytest.approx(0.1)


def test_max_iterations_ge_1() -> None:
    with pytest.raises(ValidationError):
        FitOptions(max_iterations=0)
    opts = FitOptions(max_iterations=1)
    assert opts.max_iterations == 1


def test_max_iterations_negative() -> None:
    with pytest.raises(ValidationError):
        FitOptions(max_iterations=-1)


def test_tolerance_non_negative() -> None:
    with pytest.raises(ValidationError):
        FitOptions(tolerance=-0.1)
    opts = FitOptions(tolerance=0.0)
    assert opts.tolerance == pytest.approx(0.0)


def test_delta0_strictly_positive() -> None:
    with pytest.raises(ValidationError):
        FitOptions(delta0=0.0)
    opts = FitOptions(delta0=1e-6)
    assert opts.delta0 == pytest.approx(1e-6)


def test_max_delta_strictly_positive() -> None:
    with pytest.raises(ValidationError):
        FitOptions(max_delta=0.0)
    opts = FitOptions(max_delta=0.1)
    assert opts.max_delta == pytest.approx(0.1)


def test_eta_in_half_open_interval() -> None:
    """`eta` is bounded to `[0, 0.25)`, not `[0, 1)`.

    The trust-region driver's own invariant only shrinks `Δ` when `ρ < 0.25`,
    so an `eta >= 0.25` would open a band in which a step is rejected without
    shrinking the radius and could spin to `max_nfev` — matched here by a
    `debug_assert!(eta < 0.25)` in `crates/spectrafit-trust-region`.
    """
    with pytest.raises(ValidationError):
        FitOptions(eta=1.0)
    with pytest.raises(ValidationError):
        FitOptions(eta=0.25)
    with pytest.raises(ValidationError):
        FitOptions(eta=-0.1)
    opts_zero = FitOptions(eta=0.0)
    assert opts_zero.eta == pytest.approx(0.0)
    opts_hi = FitOptions(eta=0.2499)
    assert opts_hi.eta == pytest.approx(0.2499)


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        FitOptions(unknown_field=True)  # type: ignore[call-arg]  # ty: ignore[unknown-argument]


def test_model_dump_round_trip() -> None:
    original = FitOptions()
    dumped = original.model_dump()
    restored = FitOptions.model_validate(dumped)
    assert restored == original


def test_jacobian_accepts_both_modes() -> None:
    """`jacobian` is the Rust `JacobianMode` wire string (#93)."""
    assert FitOptions(jacobian="analytic").jacobian == "analytic"
    assert FitOptions(jacobian="finite_difference").jacobian == "finite_difference"


def test_jacobian_rejects_unknown_mode() -> None:
    with pytest.raises(ValidationError):
        FitOptions(jacobian="numeric")  # type: ignore[arg-type]  # ty: ignore[invalid-argument-type]


def test_jacobian_serialises_to_the_rust_wire_string() -> None:
    """The JSON handed to the Rust core carries the snake_case mode string."""
    dumped = FitOptions(jacobian="finite_difference").model_dump_json()
    assert '"jacobian":"finite_difference"' in dumped
    assert '"jacobian":"analytic"' in FitOptions().model_dump_json()


def test_payload_without_jacobian_validates_as_analytic() -> None:
    """A payload written before the field existed still validates (default)."""
    restored = FitOptions.model_validate({"solver": "lm", "max_iterations": 50})
    assert restored.jacobian == "analytic"
