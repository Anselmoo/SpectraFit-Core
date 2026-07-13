"""G5 — _sanitize() must annotate suppressed non-finite values.

TDD: red-first. The unit tests here exercise the annotation contract:

- A non-finite float in a dict value is nulled AND a sibling ``*_suppressed``
  annotation string is added.
- Finite values are untouched (no spurious annotations added).
- The output is JSON-valid with ``allow_nan=False``.
- Deeply nested non-finites are annotated at their level.
- Non-dict structures (lists, scalars) still work (no crash, no annotation for
  non-dict containers — annotation only makes sense where a sibling key exists).
"""

from __future__ import annotations

import json

from oracles.audit.runner import _sanitize


# ---------------------------------------------------------------------------
# Annotation contract
# ---------------------------------------------------------------------------


def test_inf_in_dict_is_nulled_and_annotated() -> None:
    """A +inf value is replaced by None AND a *_suppressed sibling is added."""
    result = _sanitize({"max_abs_delta": float("inf")})
    assert isinstance(result, dict)
    sanitized: dict = result
    assert sanitized["max_abs_delta"] is None, "inf should be nulled"
    assert "max_abs_delta_suppressed" in sanitized, (
        "missing sibling annotation for nulled inf"
    )
    annotation = sanitized["max_abs_delta_suppressed"]
    assert isinstance(annotation, str)
    assert "inf" in annotation.lower(), "annotation should mention inf"


def test_neg_inf_in_dict_is_nulled_and_annotated() -> None:
    """-inf is treated the same way as +inf: nulled + annotated."""
    result = _sanitize({"score": float("-inf")})
    assert isinstance(result, dict)
    sanitized: dict = result
    assert sanitized["score"] is None
    assert "score_suppressed" in sanitized
    annotation = sanitized["score_suppressed"]
    assert isinstance(annotation, str)
    assert "inf" in annotation.lower()


def test_nan_in_dict_is_nulled_and_annotated() -> None:
    """NaN is nulled and a sibling annotation is added."""
    result = _sanitize({"residual": float("nan")})
    assert isinstance(result, dict)
    sanitized: dict = result
    assert sanitized["residual"] is None
    assert "residual_suppressed" in sanitized
    annotation = sanitized["residual_suppressed"]
    assert isinstance(annotation, str)
    assert "nan" in annotation.lower()


def test_finite_dict_gets_no_annotations() -> None:
    """A fully-finite dict must come out unchanged — no spurious *_suppressed keys."""
    original = {"max_abs_delta": 0.001, "n_cases": 12, "label": "ok", "flag": True}
    result = _sanitize(original)
    assert isinstance(result, dict)
    sanitized: dict = result
    assert sanitized == original, "finite dict must be unchanged"
    suppressed_keys = [k for k in sanitized if k.endswith("_suppressed")]
    assert suppressed_keys == [], (
        f"no *_suppressed keys expected for a finite dict; got {suppressed_keys}"
    )


def test_none_value_gets_no_annotation() -> None:
    """A pre-existing None value is not annotated (it is already null)."""
    original = {"value": None, "label": "missing"}
    result = _sanitize(original)
    assert isinstance(result, dict)
    sanitized: dict = result
    assert sanitized["value"] is None
    assert "value_suppressed" not in sanitized


def test_mixed_dict_annotates_only_nonfinite() -> None:
    """Only the non-finite key gets a sibling; finite siblings are untouched."""
    data = {"good": 1.23, "bad": float("inf"), "label": "mixed"}
    result = _sanitize(data)
    assert isinstance(result, dict)
    sanitized: dict = result
    assert sanitized["good"] == 1.23
    assert sanitized["label"] == "mixed"
    assert sanitized["bad"] is None
    assert "bad_suppressed" in sanitized
    assert "good_suppressed" not in sanitized
    assert "label_suppressed" not in sanitized


# ---------------------------------------------------------------------------
# Nested structures
# ---------------------------------------------------------------------------


def test_nested_dict_annotates_at_correct_level() -> None:
    """A non-finite value inside a nested dict gets a sibling at its own level."""
    data = {"outer": {"inner": float("nan"), "ok": 1.0}}
    result = _sanitize(data)
    assert isinstance(result, dict)
    sanitized: dict = result
    inner_dict = sanitized["outer"]
    assert isinstance(inner_dict, dict)
    inner: dict = inner_dict
    assert inner["inner"] is None
    assert "inner_suppressed" in inner
    assert inner["ok"] == 1.0
    assert "ok_suppressed" not in inner


def test_list_of_floats_nans_are_nulled_no_annotation() -> None:
    """Non-finite values inside lists are nulled (no annotation — no sibling key context)."""
    data = [1.0, float("nan"), 3.0]
    result = _sanitize(data)
    assert result == [1.0, None, 3.0]


def test_list_of_dicts_each_annotated() -> None:
    """Each dict inside a list gets its own annotation when it has non-finite floats."""
    data = [{"v": float("inf")}, {"v": 2.0}]
    result = _sanitize(data)
    assert isinstance(result, list)
    sanitized: list = result
    first = sanitized[0]
    assert isinstance(first, dict)
    item0: dict = first
    second = sanitized[1]
    assert isinstance(second, dict)
    item1: dict = second
    assert item0["v"] is None
    assert "v_suppressed" in item0
    assert item1["v"] == 2.0
    assert "v_suppressed" not in item1


# ---------------------------------------------------------------------------
# JSON-validity guard
# ---------------------------------------------------------------------------


def test_output_is_json_valid_after_sanitize() -> None:
    """After _sanitize, json.dumps(allow_nan=False) must succeed (no Inf/NaN leak)."""
    data = {
        "max_abs_delta": float("inf"),
        "residual": float("nan"),
        "score": float("-inf"),
        "finite_val": 42.0,
    }
    result = _sanitize(data)
    # Must not raise
    serialised = json.dumps(result, allow_nan=False)
    parsed = json.loads(serialised)
    assert parsed["max_abs_delta"] is None
    assert parsed["residual"] is None
    assert parsed["score"] is None
    assert parsed["finite_val"] == 42.0


# ---------------------------------------------------------------------------
# Scalar pass-through
# ---------------------------------------------------------------------------


def test_scalar_inf_outside_dict_is_nulled_no_annotation() -> None:
    """A bare float inf (not inside a dict) is still nulled; no annotation possible."""
    assert _sanitize(float("inf")) is None
    assert _sanitize(float("-inf")) is None
    assert _sanitize(float("nan")) is None


def test_finite_scalar_pass_through() -> None:
    """Finite scalars, booleans, strings, None, int — pass through unchanged."""
    assert _sanitize(3.14) == 3.14
    assert _sanitize(0) == 0
    assert _sanitize("hello") == "hello"
    assert _sanitize(True) is True
    assert _sanitize(None) is None


# ---------------------------------------------------------------------------
# Idempotency: annotation key values are finite strings → no second-pass loop
# ---------------------------------------------------------------------------


def test_annotation_value_is_a_string_not_float() -> None:
    """The *_suppressed annotation value is a string, not a float — no re-suppression."""
    result = _sanitize({"x": float("inf")})
    assert isinstance(result, dict)
    sanitized: dict = result
    suppressed_val = sanitized.get("x_suppressed")
    assert isinstance(suppressed_val, str), (
        f"annotation must be a string, not {type(suppressed_val)}"
    )
    # Verify it survives a second pass without change (idempotent on the annotation).
    result2 = _sanitize(result)
    assert isinstance(result2, dict)
    sanitized2: dict = result2
    assert sanitized2.get("x_suppressed") == suppressed_val
