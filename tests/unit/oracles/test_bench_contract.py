"""Structural owner tests for ``oracles.bench_contract`` (the frozen contract).

This file owns the WHOLE-CONTRACT structural invariants — properties that must
hold for EVERY model in the module, discovered programmatically (no hand-kept
model list), so the 40th model is covered the day it is added:

* every model inherits the ``_Base`` config (camelCase alias generator,
  ``populate_by_name``, ``extra="forbid"``);
* every field's wire alias is the exact camelCase of its snake_case name
  (deliberate wire-compat deviations are whitelisted explicitly below);
* a minimally-constructed instance of every model round-trips through
  ``model_validate(model_dump(by_alias=True))`` unchanged;
* additive-field defaults on ``BenchReport`` / ``ManifestSignals`` fill in
  (the old-payload convention relies on this);
* ``SCHEMA_VERSION`` is the max/last entry of the ``SUPPORTED_SCHEMA`` window;
* no field anywhere in the contract is typed ``Any``.

Deliberately NOT duplicated here (owned elsewhere):

* per-instance camelCase key spot-checks + synth-report round-trips —
  ``tests/unit/benchmark/test_contract.py``;
* the repo-wide ``extra="forbid"`` audit — ``tests/parity/test_extra_forbid_audit.py``
  (this file additionally pins _Base *inheritance*, which that audit does not);
* ``SuiteMetric`` non-finite validator behaviour —
  ``tests/unit/benchmark/test_wave_a_non_finite.py`` (the one visibly-enforced
  finiteness invariant NOT covered there — ManifestSignals HM ≤ GM — is here);
* the GATE_STATES / KNOWN_SOLVER_IDS rosters —
  ``tests/parity/test_canonical_wire_strings.py``.
"""

from __future__ import annotations

import inspect
from types import NoneType, UnionType
from typing import Any, Literal, Union, get_args, get_origin

import pytest
from pydantic import BaseModel, ValidationError
from pydantic.alias_generators import to_camel
from pydantic.fields import FieldInfo

import oracles.bench_contract as bench_contract
from oracles.bench_contract import (
    SCHEMA_VERSION,
    SUPPORTED_SCHEMA,
    BenchReport,
    ManifestSignals,
    _Base,
)

# ---------------------------------------------------------------------------
# Programmatic model discovery — the point of this file: no hand-kept list.
# ---------------------------------------------------------------------------


def _contract_models() -> list[tuple[str, type[BaseModel]]]:
    """Every pydantic model DEFINED in oracles.bench_contract (not re-exports)."""
    found = [
        (name, cls)
        for name, cls in inspect.getmembers(bench_contract, inspect.isclass)
        if issubclass(cls, BaseModel) and cls.__module__ == bench_contract.__name__
    ]
    assert found, "model discovery walked an empty module — walker regressed"
    for _, cls in found:
        # Models with forward references to later-defined classes (e.g.
        # Summary.speedup_ci: CI) defer their build; without a rebuild,
        # model_fields exposes FieldInfo with the alias generator NOT yet
        # applied, which would false-positive the alias-drift test.
        cls.model_rebuild()
    return found


MODELS: list[tuple[str, type[BaseModel]]] = _contract_models()
MODEL_IDS: list[str] = [name for name, _ in MODELS]

# Deliberate wire-format deviations from to_camel, whitelisted per step-5
# policy (exempt explicitly, never silently). Each carries an explicit
# Field(serialization_alias=..., validation_alias=...) in the module because
# the web/TS side reads these EXACT literals:
#   - dAIC / dBIC: information-criterion deltas keep the domain-standard
#     capitalisation (to_camel would emit "dAic"/"dBic").
#   - Ngrid: the mockup/window.BENCH key predates the alias generator and is
#     pinned by test_camelcase_aliases_match_mockup_keys.
_ALIAS_EXEMPT: dict[tuple[str, str], str] = {
    ("Summary", "d_aic"): "dAIC",
    ("Summary", "d_bic"): "dBIC",
    ("SelectionStats", "d_aic"): "dAIC",
    ("SelectionStats", "d_bic"): "dBIC",
    ("Featured", "n_grid"): "Ngrid",
}


def _serialization_key(field_name: str, info: FieldInfo) -> str:
    """The key this field writes on the wire under model_dump(by_alias=True)."""
    if info.serialization_alias is not None:
        return info.serialization_alias
    if info.alias is not None:
        return info.alias
    return field_name


def _validation_key(field_name: str, info: FieldInfo) -> str:
    """The alias key this field accepts on validation."""
    if info.validation_alias is not None:
        # The contract only ever uses plain-string aliases (no AliasChoices);
        # pin that too so validation/serialization can't silently diverge.
        assert isinstance(info.validation_alias, str), (
            f"{field_name}: contract fields must use plain-string "
            f"validation aliases, got {info.validation_alias!r}"
        )
        return info.validation_alias
    if info.alias is not None:
        return info.alias
    return field_name


# ---------------------------------------------------------------------------
# Minimal-instance builder — required fields only, so defaults are exercised.
# ---------------------------------------------------------------------------

_SCALAR_VALUES: dict[type, object] = {bool: True, int: 1, float: 1.0, str: "x"}


def _minimal_value(annotation: object) -> object:
    """A minimal valid value for a contract field annotation."""
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        args = get_args(annotation)
        if NoneType in args:
            return None
        return _minimal_value(args[0])
    if origin is Literal:
        return get_args(annotation)[0]
    if origin is list:
        return []
    if origin is dict:
        return {}
    if origin is tuple:
        return tuple(
            _minimal_value(arg) for arg in get_args(annotation) if arg is not Ellipsis
        )
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _minimal_instance(annotation)
    if isinstance(annotation, type) and annotation in _SCALAR_VALUES:
        return _SCALAR_VALUES[annotation]
    raise AssertionError(
        f"no minimal-value strategy for annotation {annotation!r} — "
        "a new field type entered the contract; extend the builder"
    )


def _minimal_instance(cls: type[BaseModel]) -> BaseModel:
    """Construct cls with only its required fields, minimally filled."""
    kwargs = {
        field_name: _minimal_value(info.annotation)
        for field_name, info in cls.model_fields.items()
        if info.is_required()
    }
    return cls(**kwargs)


# ---------------------------------------------------------------------------
# Sanity: the walker actually sees the contract.
# ---------------------------------------------------------------------------


def test_discovery_finds_the_known_core_models() -> None:
    names = set(MODEL_IDS)
    expected_sample = {
        "BenchReport",
        "Featured",
        "BackendProfile",
        "SuiteMetric",
        "SuiteCase",
        "ManifestSignals",
        "InferenceBlock",
        "PanelSpec",
    }
    missing = expected_sample - names
    assert not missing, f"discovery walker missed core models: {missing}"
    # 39 models as of schema 1.7; growth is fine, shrinkage means the walker
    # (or the contract) lost models.
    assert len(MODELS) >= 35, f"only {len(MODELS)} models discovered"


# ---------------------------------------------------------------------------
# Invariant 1: every model inherits the _Base wire config.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "cls"), MODELS, ids=MODEL_IDS)
def test_model_inherits_base_wire_config(name: str, cls: type[BaseModel]) -> None:
    if cls is not _Base:
        assert issubclass(cls, _Base), (
            f"{name} does not inherit _Base — it will not camelize/forbid on "
            "the wire like every other contract model"
        )
    config = cls.model_config
    assert config.get("extra") == "forbid", f"{name}: extra != 'forbid'"
    assert config.get("alias_generator") is to_camel, (
        f"{name}: alias_generator is not pydantic.alias_generators.to_camel"
    )
    assert config.get("populate_by_name") is True, (
        f"{name}: populate_by_name is not True (snake_case inputs would break)"
    )


# ---------------------------------------------------------------------------
# Invariant 2: every field's alias is the exact camelCase of its name.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "cls"), MODELS, ids=MODEL_IDS)
def test_every_field_alias_is_exact_camelcase(name: str, cls: type[BaseModel]) -> None:
    mismatches: list[str] = []
    for field_name, info in cls.model_fields.items():
        expected = _ALIAS_EXEMPT.get((name, field_name), to_camel(field_name))
        ser = _serialization_key(field_name, info)
        val = _validation_key(field_name, info)
        if ser != expected or val != expected:
            mismatches.append(
                f"{name}.{field_name}: serialization={ser!r} "
                f"validation={val!r} expected={expected!r}"
            )
    assert not mismatches, "alias drift:\n  " + "\n  ".join(mismatches)


def test_alias_exemptions_still_exist() -> None:
    """Every whitelisted deviation still points at a real field (no stale row)."""
    by_name = dict(MODELS)
    for (model_name, field_name), alias in _ALIAS_EXEMPT.items():
        cls = by_name.get(model_name)
        assert cls is not None, f"exemption for unknown model {model_name}"
        info = cls.model_fields.get(field_name)
        assert info is not None, (
            f"exemption for unknown field {model_name}.{field_name}"
        )
        assert _serialization_key(field_name, info) == alias


# ---------------------------------------------------------------------------
# Invariant 3: alias round-trip is the identity for every model.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("name", "cls"), MODELS, ids=MODEL_IDS)
def test_alias_round_trip_is_identity(name: str, cls: type[BaseModel]) -> None:
    instance = _minimal_instance(cls)
    dumped = instance.model_dump(by_alias=True)
    revalidated = cls.model_validate(dumped)
    assert revalidated == instance, f"{name}: round-trip changed the instance"
    assert revalidated.model_dump(by_alias=True) == dumped, (
        f"{name}: second dump differs from first (lossy round-trip)"
    )


# ---------------------------------------------------------------------------
# Invariant 4: additive-field defaults fill in (old-payload convention).
# ---------------------------------------------------------------------------


def test_bench_report_additive_defaults_fill_in() -> None:
    report = BenchReport(solvers=[], categories=[], analyzed=[], suite=[])
    assert report.schema_version == SCHEMA_VERSION
    assert report.baseline_solver_id == "lmfit"
    assert report.manifest is None
    assert report.trust_block is None
    assert report.panels == []
    assert report.inference is None
    assert report.git_commit is None
    assert report.git_branch is None
    assert report.run_timestamp_unix is None


def test_manifest_signals_additive_defaults_fill_in() -> None:
    signals = ManifestSignals(
        geomean_speedup_vs_baseline=2.0,
        max_abs_delta_r2=1e-5,
        spectrafit_win_rate=0.9,
        regressions=0,
    )
    assert signals.pinned is None
    assert signals.harmonic_mean_speedup_vs_baseline is None
    assert signals.gate_state is None
    assert signals.nonfinite_dr2_case_ids == []
    assert signals.saturated_categories == []
    assert signals.sanitized_value_paths == []


@pytest.mark.parametrize(("name", "cls"), MODELS, ids=MODEL_IDS)
def test_defaulted_fields_never_share_mutable_state(
    name: str, cls: type[BaseModel]
) -> None:
    """Two required-only instances must not alias each other's list/dict defaults."""
    a = _minimal_instance(cls)
    b = _minimal_instance(cls)
    for field_name, info in cls.model_fields.items():
        if info.is_required():
            continue
        value_a = getattr(a, field_name)
        if isinstance(value_a, (list, dict)):
            assert value_a is not getattr(b, field_name), (
                f"{name}.{field_name}: mutable default shared between instances"
            )


# ---------------------------------------------------------------------------
# Invariant 5: the schema window is coherent.
# ---------------------------------------------------------------------------


def test_schema_version_is_last_and_max_of_supported_window() -> None:
    def version_key(version: str) -> tuple[int, ...]:
        return tuple(int(part) for part in version.split("."))

    assert SCHEMA_VERSION in SUPPORTED_SCHEMA
    assert SUPPORTED_SCHEMA[-1] == SCHEMA_VERSION, (
        "SCHEMA_VERSION must be the last entry of the SUPPORTED_SCHEMA window"
    )
    assert max(SUPPORTED_SCHEMA, key=version_key) == SCHEMA_VERSION
    assert list(SUPPORTED_SCHEMA) == sorted(SUPPORTED_SCHEMA, key=version_key), (
        "SUPPORTED_SCHEMA window must be ordered oldest → newest"
    )
    assert len(set(SUPPORTED_SCHEMA)) == len(SUPPORTED_SCHEMA), (
        "SUPPORTED_SCHEMA contains duplicate versions"
    )


# ---------------------------------------------------------------------------
# Invariant 6: the contract is Any-free.
# ---------------------------------------------------------------------------


def _annotation_leaves(annotation: object):
    yield annotation
    for arg in get_args(annotation):
        if arg is not Ellipsis:
            yield from _annotation_leaves(arg)


def test_no_contract_field_is_typed_any() -> None:
    offenders = [
        f"{name}.{field_name}"
        for name, cls in MODELS
        for field_name, info in cls.model_fields.items()
        if any(leaf is Any for leaf in _annotation_leaves(info.annotation))
    ]
    assert not offenders, (
        "contract fields typed Any (the contract is Any-free — keep it so):\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# Visibly-enforced finiteness invariant not owned elsewhere: HM ≤ GM.
# (SuiteMetric's non-finite validators are owned by test_wave_a_non_finite.py.)
# ---------------------------------------------------------------------------


def test_manifest_signals_rejects_harmonic_mean_above_geomean() -> None:
    with pytest.raises(ValidationError, match="exceeds geometric mean"):
        ManifestSignals(
            geomean_speedup_vs_baseline=2.0,
            max_abs_delta_r2=1e-5,
            spectrafit_win_rate=0.9,
            regressions=0,
            harmonic_mean_speedup_vs_baseline=3.0,
        )


def test_manifest_signals_accepts_harmonic_mean_at_or_below_geomean() -> None:
    signals = ManifestSignals(
        geomean_speedup_vs_baseline=2.0,
        max_abs_delta_r2=1e-5,
        spectrafit_win_rate=0.9,
        regressions=0,
        harmonic_mean_speedup_vs_baseline=2.0,  # equality is legal (all equal)
    )
    assert signals.harmonic_mean_speedup_vs_baseline == 2.0
