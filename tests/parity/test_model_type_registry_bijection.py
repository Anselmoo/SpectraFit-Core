"""Parity gate: ModelType ↔ MODEL_REGISTRY bijection.

Enforces three properties:
1. Every MODEL_REGISTRY entry's spectrafit_type resolves to a valid ModelType member.
2. Every ModelType member except the known multi-dim showcases is registered.
3. Tri-parity: ModelType[spectrafit_type] == member (name lookup round-trips).
4. The exemption set is exactly the documented showcases — no silent growth.
"""

from __future__ import annotations

from spectrafit_core.models import ModelType
from oracles.models import MODEL_REGISTRY

_MULTIDIM_EXEMPTIONS: frozenset[str] = frozenset({"GAUSSIAN2D", "GAUSSIAN_ND"})

_MT_NAMES: frozenset[str] = frozenset(m.name for m in ModelType)
_REG_SFT: frozenset[str] = frozenset(m.spectrafit_type for m in MODEL_REGISTRY.values())


def test_every_registry_entry_maps_to_valid_modeltype() -> None:
    """All registry entries have a spectrafit_type that resolves to a ModelType member."""
    orphans = _REG_SFT - _MT_NAMES
    assert not orphans, f"Registry entries with no ModelType: {sorted(orphans)}"


def test_every_modeltype_except_showcases_is_registered() -> None:
    """All ModelType members except multi-dim showcases appear in MODEL_REGISTRY."""
    unregistered = _MT_NAMES - _REG_SFT - _MULTIDIM_EXEMPTIONS
    assert not unregistered, (
        f"ModelType members missing from MODEL_REGISTRY: {sorted(unregistered)}\n"
        f"If intentional, add to _MULTIDIM_EXEMPTIONS."
    )


def test_exemption_set_is_exactly_multidim_showcases() -> None:
    """The gap between ModelType and registry is exactly _MULTIDIM_EXEMPTIONS."""
    actual_gap = _MT_NAMES - _REG_SFT
    assert actual_gap == _MULTIDIM_EXEMPTIONS, (
        f"Expected gap {_MULTIDIM_EXEMPTIONS}, got {actual_gap}.\n"
        "Either update _MULTIDIM_EXEMPTIONS or register the new model."
    )


def test_tri_parity_spectrafit_type_resolves_to_modeltype() -> None:
    """PeakModel.spectrafit_type round-trips through ModelType[name].name."""
    for key, pm in MODEL_REGISTRY.items():
        member = ModelType[pm.spectrafit_type]
        assert member.name == pm.spectrafit_type, (
            f"Registry key {key!r}: spectrafit_type={pm.spectrafit_type!r} "
            f"round-trips to {member.name!r}"
        )
