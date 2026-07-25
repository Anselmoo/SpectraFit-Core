"""Tests for lineshape recipe builders in oracles.lineshapes.

Covers all 20 registered lineshape builders: unit tests for
build(rng, variant) -> (components, description) return contracts,
component pydantic serialization, and registry completeness.
"""

from __future__ import annotations

import random

import pytest

from oracles.lineshapes import LINESHAPE_RECIPE_REGISTRY

# All 20 lineshape recipes and their correct test variants.
_LINESHAPE_PARAMS: list[tuple[str, str]] = [
    ("asym_ir", ""),
    ("breit_wigner", ""),
    ("cauchy_dispersion", ""),
    ("harmonic_ir", ""),
    ("ir_voigt", "2"),
    ("k_edge", ""),
    ("kww", ""),
    ("l_edge", ""),
    ("mgh09_rational", ""),
    ("mixed_asym", ""),
    ("moffat", ""),
    ("power_law_offset", ""),
    ("power_saturation", ""),
    ("saturating_exponential", ""),
    ("single", "true_voigt"),
    ("split_gauss", ""),
    ("split_p7", ""),
    ("students_t", ""),
    ("tauc", ""),
    ("xps_doublet", ""),
]


@pytest.mark.parametrize(
    "recipe,variant", _LINESHAPE_PARAMS, ids=[p[0] for p in _LINESHAPE_PARAMS]
)
def test_build_returns_nonempty_list_and_description(recipe: str, variant: str) -> None:
    """Test that build(rng, variant) returns (list[components], str description)."""
    rng = random.Random(42)
    build_fn = LINESHAPE_RECIPE_REGISTRY[recipe]
    components, description = build_fn(rng, variant)

    assert isinstance(components, list)
    assert len(components) >= 1
    assert isinstance(description, str)
    assert len(description) > 0


@pytest.mark.parametrize(
    "recipe,variant", _LINESHAPE_PARAMS, ids=[p[0] for p in _LINESHAPE_PARAMS]
)
def test_build_components_are_pydantic_models(recipe: str, variant: str) -> None:
    """Test that each component is a Pydantic BaseModel that can serialize."""
    rng = random.Random(42)
    build_fn = LINESHAPE_RECIPE_REGISTRY[recipe]
    components, _ = build_fn(rng, variant)

    for component in components:
        assert hasattr(component, "model_dump"), (
            f"Component from {recipe} does not have model_dump method"
        )
        # Ensure serialization does not raise.
        component.model_dump()


def test_registry_contains_all_expected_keys() -> None:
    """Test that the registry has exactly the 20 expected lineshape keys."""
    expected_keys = {p[0] for p in _LINESHAPE_PARAMS}
    assert set(LINESHAPE_RECIPE_REGISTRY.keys()) == expected_keys
