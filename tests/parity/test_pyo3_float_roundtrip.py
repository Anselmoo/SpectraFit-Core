r"""Floats must survive the PyO3 JSON boundary bit-identically — or fail loudly.

Every ``#[pyfunction]`` in this repo returns a JSON string (the
``pre-merge-pyO3`` hook enforces it), so every number crossing the Rust <->
Python boundary is serialised to text and re-parsed. This module pins two
properties of that seam:

1. A finite ``f64`` survives bit-for-bit (no precision truncation from a
   fixed-precision serialiser).
2. A non-finite value (``NaN``/``+-inf``) has *defined* behaviour — never a
   silent, indistinguishable-from-legitimate ``None``/``0.0``.

Entry point: ``spectrafit_core._core.evaluate_components`` (via
``FitGraph.eval_components``), evaluating a single ``constant`` node
(``f(x) = c``, `crates/spectrafit-models/src/polynomial.rs`) — the narrowest
``#[pyfunction]`` that carries a caller-chosen float across the boundary and
back with **no arithmetic in between**.

``evaluate`` (the *summed* sibling used by ``FitGraph.eval``) was rejected as
the round-trip vehicle: it accumulates node contributions into a ``0.0``
accumulator, and IEEE-754 addition turns ``-0.0`` into ``0.0`` on its own
(``0.0 + -0.0 == 0.0``) before serialisation is ever reached. That is a real,
reproducible sign-loss — but it is a solver-side *arithmetic* effect, not a
JSON *serialisation* effect, and this suite is scoped to the wire itself.
``evaluate_components`` (per-node, no summation) isolates the seam cleanly;
confirmed empirically against ``evaluate`` before writing this suite.

**Fixed defect (see ``test_finite_float_survives_the_json_boundary`` and
``test_known_large_magnitude_value_loses_one_ulp_on_parse`` below, now
ordinary passing assertions):** finite floats used to *not* survive
bit-identically. Root cause, traced to the source: `Cargo.toml` pinned
``serde_json = "1"`` without the crate's ``float_roundtrip`` feature. Per
serde_json's own documentation, that feature trades ~2x parse speed for
*correctly-rounded* float parsing; without it, ``serde_json::from_str`` used
a faster best-effort parser that could be off by 1 ULP. Serialisation (Rust
f64 -> JSON text, via `ryu`) and Python's own ``json`` module (both
directions) are exact — the loss was specifically in `serde_json`'s
*default* float *parser*, i.e. every `#[pyfunction]` argument string it
deserialises (`graph_json`, `params_json`, `data_json`, `options_json`), not
the JSON it emits. `Cargo.toml`'s workspace `serde_json` dependency now
enables `float_roundtrip`. Pre-fix, a sweep of 2000 random f64 bit patterns
through this same entry point measured roughly a 29% failure rate
(589/2000), each off by exactly 1 ULP; the same post-fix sweep measured
0/2000.
"""

from __future__ import annotations

import math
import struct
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st
from spectrafit_core import (
    FitGraph,
    MeasurementData,
    ModelNodeSpec,
    ModelType,
    Parameter,
)

_GRAPH = FitGraph(
    nodes=[
        ModelNodeSpec(
            id="c",
            model_type=ModelType.CONSTANT,
            parameters={"c": Parameter(value=0.0)},
        ),
    ],
)
_DATA = MeasurementData(x=[0.0], y=[0.0])


def _roundtrip_through_core(value: float) -> float:
    """Send ``value`` through ``core.evaluate_components`` and read it back.

    ``evaluate_components`` evaluates the ``constant`` node's kernel
    (``f(x) = c``) — an identity pass with no arithmetic — so any drift
    between the value sent and the value recovered is attributable only to
    the JSON serialise/parse round trip, never to floating-point arithmetic
    on the Rust side.
    """
    components = _GRAPH.eval_components({"c.c": value}, _DATA)
    return float(components["c"][0])


@given(value=st.floats(allow_nan=False, allow_infinity=False, width=64))
def test_finite_float_survives_the_json_boundary(value: float) -> None:
    """A finite f64 round-trips bit-for-bit through the Rust JSON contract.

    Compared via ``struct.pack`` (not ``==``): ``==`` cannot distinguish
    ``-0.0`` from ``0.0`` and treats ``NaN`` as unequal to itself, either of
    which would hide a real precision-loss bug. Previously ``xfail(strict)``
    pinning a confirmed defect (`Cargo.toml`'s `serde_json = "1"` without the
    `float_roundtrip` feature — see the module docstring); fixed by enabling
    that feature, verified by re-running the same 2000-random-f64 sweep
    described in the module docstring post-fix: 0/2000 losses.
    """
    recovered = _roundtrip_through_core(value)
    assert struct.pack("<d", recovered) == struct.pack("<d", value)


def test_known_large_magnitude_value_loses_one_ulp_on_parse() -> None:
    """Pinned regression case for the serde_json non-`float_roundtrip` defect.

    Was ``xfail(strict=True)``: 5.114226694005648e+71 in,
    5.114226694005649e+71 out (the next f64 up, 1 ULP), traced to
    `serde_json::from_str`'s default best-effort float parser. Fixed by
    enabling `serde_json`'s `float_roundtrip` feature in the workspace
    `Cargo.toml`; this value now round-trips bit-for-bit.
    """
    value = 5.114226694005648e71
    recovered = _roundtrip_through_core(value)
    assert struct.pack("<d", recovered) == struct.pack("<d", value)


@pytest.mark.parametrize(
    "value",
    [
        -0.0,
        sys.float_info.max,
        sys.float_info.min,
        5e-324,  # smallest positive subnormal
    ],
    ids=["neg_zero", "float_max", "float_min_normal", "smallest_subnormal"],
)
def test_finite_edge_values_survive_bit_identically(value: float) -> None:
    """Explicit edge cases called out in the V&V hardening plan (Task 5).

    ``-0.0`` in particular: verified separately that it survives Python's own
    ``json.dumps``/``json.loads`` perfectly on its own, and that
    ``evaluate_components`` (no summation) preserves the sign bit across the
    Rust round trip too — it is only ``evaluate``'s summation accumulator
    that loses it (see module docstring).
    """
    recovered = _roundtrip_through_core(value)
    assert struct.pack("<d", recovered) == struct.pack("<d", value)


@pytest.mark.parametrize(
    "value",
    [math.nan, math.inf, -math.inf],
    ids=["nan", "inf", "neg_inf"],
)
def test_non_finite_input_is_rejected_not_silently_coerced(value: float) -> None:
    """A non-finite *input* parameter must error, never arrive as ``0.0``.

    Python's ``json.dumps`` happily emits the non-standard ``NaN`` /
    ``Infinity`` / ``-Infinity`` tokens (``allow_nan=True`` is the default).
    Rust's ``serde_json`` parser is strict JSON and rejects them outright, so
    the failure mode actually observed is a loud ``ValueError`` raised from
    the ``#[pyfunction]`` — not a silent truncation to ``0.0`` and not a
    successful call. Pinned here so a future change to either serialiser
    cannot silently swap this for data loss.
    """
    with pytest.raises(ValueError, match="JSON parse error"):
        _roundtrip_through_core(value)


def test_non_finite_kernel_output_collapses_to_null_not_zero() -> None:
    """A non-finite value the *Rust kernel itself* produces survives as JSON null.

    Unlike a caller-supplied NaN/Inf (rejected at parse time, see above), a
    value that becomes non-finite *inside* the Rust computation is not caught
    by any parse-time guard: ``serde_json`` serialises a non-finite ``f64``
    as JSON ``null``. This is *not* the ``0.0``-substitution guard documented
    in ``crates/spectrafit-solver/src/postfit.rs`` (``apply_finiteness_guards``,
    "EF-RUST-02") — that guard is scoped to the derived scalars
    ``chi2``/``r_squared``/``reduced_chi2``/``aic``/``bic`` assembled by
    ``fit()``, not to raw model output from ``evaluate``/``evaluate_components``.

    ``quadratic``'s kernel (``amplitude * (x - center)**2 + offset``,
    `crates/spectrafit-models/src/polynomial.rs`) overflows f64 for
    ``amplitude = sys.float_info.max`` at ``x = 2.0`` (``max * 4 > f64::MAX``)
    — no NaN/Inf was ever sent in; the Rust arithmetic produced it internally.

    This is the finding this test exists to pin, not fix: on the wire, that
    ``null`` is bit-for-bit indistinguishable from "value legitimately
    absent" — the same JSON shape ``FitResult.condition_number`` and
    ``ParameterResult.stderr`` (both ``float | None``) use for "the solver
    did not compute this". The distinction between "was non-finite" and "was
    never computed" is lost at this seam. Whether that ambiguity is ever
    load-bearing for a caller is a separate design question; this test only
    pins that it exists today.
    """
    graph = FitGraph(
        nodes=[
            ModelNodeSpec(
                id="q",
                model_type=ModelType.QUADRATIC,
                parameters={
                    "amplitude": Parameter(value=1.0),
                    "center": Parameter(value=0.0),
                    "offset": Parameter(value=0.0),
                },
            ),
        ],
    )
    data = MeasurementData(x=[2.0], y=[0.0])
    params = {
        "q.amplitude": sys.float_info.max,
        "q.center": 0.0,
        "q.offset": 0.0,
    }

    components = graph.eval_components(params, data)

    # np.asarray(..., dtype=float) turns the JSON `null` -> Python `None` ->
    # NaN when eval_components builds its numpy array; assert the sentinel is
    # non-finite (round-trip data loss), never a silently-plausible 0.0.
    (recovered,) = components["q"]
    assert math.isnan(recovered), (
        f"expected the overflowed +inf to arrive as a NaN-via-null sentinel, "
        f"got {recovered!r} instead"
    )
