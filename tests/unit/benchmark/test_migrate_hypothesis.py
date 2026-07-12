"""Property-based tests for migration edge cases using Hypothesis.

The existing test_migrate.py is comprehensive for happy paths and registered
migrations. This module adds targeted Hypothesis property tests for edge cases
that are not already covered:

1. Identity property: migrate_report(p, from_v=v, to_v=v) returns the exact same
   object regardless of payload structure.
2. 1.5→1.6 with empty analyzed list: must not raise, and analyzed stays empty.
3. 1.5→1.6 with cases lacking timeResolved: pass-through cases stay unmodified.
4. 1.5→1.6 with N cases each having timeResolved: all renamed correctly via
   Hypothesis-generated case structures.
5. 1.6→1.7 with arbitrary multidim values: always set to None.

These tests complement the deterministic happy-path tests in test_migrate.py.
"""

from __future__ import annotations

from hypothesis import given, settings, strategies as st

from oracles.migrate import migrate_report


@given(payload=st.fixed_dictionaries({"key": st.integers()}), version=st.text(min_size=1, max_size=5))
@settings(max_examples=50)
def test_migrate_report_identity_is_same_object(payload: dict, version: str) -> None:
    """migrate_report returns the exact same object when from_v == to_v."""
    result = migrate_report(payload, from_v=version, to_v=version)
    assert result is payload


def test_1_5_to_1_6_empty_analyzed_list_does_not_raise() -> None:
    """1.5→1.6 with analyzed=[] must not raise."""
    payload = {"schemaVersion": "1.5", "analyzed": []}
    out = migrate_report(payload, from_v="1.5", to_v="1.6")
    assert out["analyzed"] == []
    assert out["schemaVersion"] == "1.6"


def test_1_5_to_1_6_case_without_time_resolved_is_unchanged() -> None:
    """A case dict that lacks 'timeResolved' is passed through unmodified."""
    case = {"id": "easy-001", "r2": 0.999}
    payload = {"schemaVersion": "1.5", "analyzed": [case]}
    out = migrate_report(payload, from_v="1.5", to_v="1.6")
    assert out["analyzed"][0] == case  # no mutation
    assert "globalFit" not in out["analyzed"][0]


@given(n=st.integers(min_value=0, max_value=5))
@settings(max_examples=30)
def test_1_5_to_1_6_all_time_resolved_keys_renamed(n: int) -> None:
    """After 1.5→1.6, no analyzed case retains 'timeResolved'."""
    cases = [
        {
            "id": f"case-{i}",
            "timeResolved": {
                "x": [0.0, 1.0],
                "times": [float(i)],
                "tLabel": f"label-{i}",
                "slices": [{"t": float(i), "obs": [1.0]}],
                "traces": [],
            },
        }
        for i in range(n)
    ]
    payload = {"schemaVersion": "1.5", "analyzed": cases}
    out = migrate_report(payload, from_v="1.5", to_v="1.6")
    for case in out["analyzed"]:
        assert "timeResolved" not in case
        assert "globalFit" in case


@given(
    multidim_val=st.one_of(
        st.fixed_dictionaries({"nx": st.integers(1, 4), "ny": st.integers(1, 4)}),
        st.fixed_dictionaries({"nDims": st.integers(2, 5)}),
        st.just({"peaks": []}),
    )
)
@settings(max_examples=50)
def test_1_6_to_1_7_any_non_none_multidim_becomes_null(multidim_val: dict) -> None:
    """Any non-None multidim value in analyzed cases is set to None by 1.6→1.7."""
    payload = {
        "schemaVersion": "1.6",
        "analyzed": [{"id": "c0", "multidim": multidim_val}],
    }
    out = migrate_report(payload, from_v="1.6", to_v="1.7")
    assert out["analyzed"][0]["multidim"] is None
