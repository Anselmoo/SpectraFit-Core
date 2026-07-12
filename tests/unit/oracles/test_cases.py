"""Owner tests for the declarative case catalog (``oracles.cases``).

Registry/spec-level class guards only — no fits are run. Complements
``test_categories.py`` (category-registry drift guards) with the catalog
invariants: case-id uniqueness and format, model-key + param-name validity
against ``MODEL_REGISTRY``, constraint referential integrity (``fixed_params``
/ ``expr_edges``), landscape↔optfn coupling, materialization determinism and
shape/finiteness, and the family→registry count wiring (counts are derived
from the generator grids, never pinned as bare magic numbers).
"""

from __future__ import annotations

import collections
import re

import numpy as np
import pytest
from pydantic import ValidationError

from oracles import cases, models

# Node-parameter references inside an expr_edge expression, e.g. "p0.sigma".
_NODE_REF = re.compile(r"\bp(\d+)\.([A-Za-z_]\w*)")


@pytest.fixture(scope="module")
def specs() -> list[cases.CaseSpec]:
    """The expanded (unmaterialized) spec list at the default seed."""
    return cases.build_specs()


@pytest.fixture(scope="module")
def catalog() -> list[cases.BenchCase]:
    """The full materialized catalog at the default seed."""
    return cases.build_catalog()


def _valid_params(component: cases.Component) -> set[str]:
    """Canonical param-name set for a component's registered model."""
    return set(models.get_model(component.model).param_names)


def _spec_kwargs(**overrides: object) -> dict[str, object]:
    """Minimal valid CaseSpec kwargs for validation-behavior tests."""
    base: dict[str, object] = {
        "id": "ZZ-001",
        "name": "unit fixture",
        "category": "easy",
        "difficulty": 0.5,
        "components": [cases.GaussianSpec(amplitude=1.0, center=0.0, sigma=0.5)],
        "x_min": -1.0,
        "x_max": 1.0,
        "n_points": 16,
        "noise": 0.01,
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# Family ↔ category-registry wiring
# --------------------------------------------------------------------------- #
def test_family_categories_biject_with_category_registry() -> None:
    """Exactly one CaseFamily per registered category — no orphans either way."""
    fam_cats = [fam.category for fam in cases.FAMILIES]
    assert len(fam_cats) == len(set(fam_cats)), "duplicate family for a category"
    assert set(fam_cats) == set(cases.CATEGORY_REGISTRY)


def test_family_counts_match_category_registry() -> None:
    """The hand-written registry counts equal the grid-derived family counts."""
    for fam in cases.FAMILIES:
        assert fam.count == cases.CATEGORY_COUNTS[fam.category], fam.category


def test_catalog_size_derives_from_family_counts(
    specs: list[cases.CaseSpec],
) -> None:
    """Total case count is derived from the family grids, not a magic number."""
    assert len(specs) == sum(fam.count for fam in cases.FAMILIES)
    assert len(specs) == sum(cases.CATEGORY_COUNTS.values())


# --------------------------------------------------------------------------- #
# Per-spec identity + taxonomy invariants
# --------------------------------------------------------------------------- #
def test_case_ids_unique_across_catalog(specs: list[cases.CaseSpec]) -> None:
    dupes = [i for i, n in collections.Counter(s.id for s in specs).items() if n > 1]
    assert not dupes, f"duplicate case ids: {dupes}"


def test_case_id_format_is_prefix_dash_ordinal(specs: list[cases.CaseSpec]) -> None:
    """Ids are '<category-prefix>-NNN' with 1..count ordinals per category."""
    prefixes = list(cases.PREFIX.values())
    assert len(prefixes) == len(set(prefixes)), "category prefixes must be unique"
    ordinals: dict[str, list[int]] = collections.defaultdict(list)
    for s in specs:
        m = re.fullmatch(rf"{re.escape(cases.PREFIX[s.category])}-(\d{{3}})", s.id)
        assert m, f"{s.id}: expected '{cases.PREFIX[s.category]}-NNN'"
        ordinals[s.category].append(int(m.group(1)))
    for cat, nums in ordinals.items():
        assert nums == list(range(1, cases.CATEGORY_COUNTS[cat] + 1)), cat


def test_every_case_category_is_registered(specs: list[cases.CaseSpec]) -> None:
    bad = {
        (s.id, s.category) for s in specs if s.category not in cases.CATEGORY_REGISTRY
    }
    assert not bad, f"cases with unregistered categories: {sorted(bad)}"


def test_spec_scalar_invariants(specs: list[cases.CaseSpec]) -> None:
    """Grid/noise/difficulty scalars stay in the ranges materialize relies on."""
    for s in specs:
        assert s.n_points > 0, s.id
        assert s.x_max > s.x_min, s.id
        assert s.noise >= 0.0, s.id
        assert s.guess_scale >= 0.0, s.id
        assert 0.0 <= s.difficulty <= 1.0, s.id


# --------------------------------------------------------------------------- #
# Component ↔ MODEL_REGISTRY validity
# --------------------------------------------------------------------------- #
def test_component_model_keys_exist_in_model_registry(
    specs: list[cases.CaseSpec],
) -> None:
    unknown = {
        (s.id, comp.model)
        for s in specs
        for comp in s.components
        if comp.model not in models.MODEL_REGISTRY
    }
    assert not unknown, f"components with unregistered model keys: {sorted(unknown)}"


def test_component_params_match_registry_param_names(
    specs: list[cases.CaseSpec],
) -> None:
    """Every component's param dict is exactly its model's canonical param set."""
    for s in specs:
        for comp in s.components:
            assert set(comp.to_params()) == _valid_params(comp), (s.id, comp.model)


# --------------------------------------------------------------------------- #
# Pydantic validation behavior (what the models must reject)
# --------------------------------------------------------------------------- #
def test_case_spec_rejects_out_of_range_difficulty() -> None:
    with pytest.raises(ValidationError):
        cases.CaseSpec(**_spec_kwargs(difficulty=1.5))


def test_case_spec_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        cases.CaseSpec(**_spec_kwargs(unknown_knob=1.0))


def test_component_union_rejects_unknown_model_key() -> None:
    """The discriminated union refuses model keys outside the typed catalog."""
    with pytest.raises(ValidationError):
        cases.CaseSpec(**_spec_kwargs(components=[{"model": "not_a_model"}]))


# --------------------------------------------------------------------------- #
# Constraint referential integrity (fixed_params / expr_edges)
# --------------------------------------------------------------------------- #
def test_fixed_params_reference_existing_nodes_and_params(
    specs: list[cases.CaseSpec],
) -> None:
    for s in specs:
        for node_id, pnames in s.fixed_params.items():
            m = re.fullmatch(r"p(\d+)", node_id)
            assert m, f"{s.id}: bad fixed_params node id {node_id!r}"
            idx = int(m.group(1))
            assert idx < len(s.components), (s.id, node_id)
            assert set(pnames) <= _valid_params(s.components[idx]), (
                s.id,
                node_id,
                pnames,
            )


def test_expr_edges_reference_existing_nodes_and_params(
    specs: list[cases.CaseSpec],
) -> None:
    """Tie edges name a real target node/param and only real source node params."""
    for s in specs:
        for edge in s.expr_edges:
            assert set(edge) == {"target_node", "target_param", "expression"}, s.id
            tm = re.fullmatch(r"p(\d+)", edge["target_node"])
            assert tm, (s.id, edge)
            t_idx = int(tm.group(1))
            assert t_idx < len(s.components), (s.id, edge)
            assert edge["target_param"] in _valid_params(s.components[t_idx]), (
                s.id,
                edge,
            )
            refs = _NODE_REF.findall(edge["expression"])
            assert refs, f"{s.id}: expression references no node param: {edge}"
            for src_idx_str, pname in refs:
                src_idx = int(src_idx_str)
                assert src_idx < len(s.components), (s.id, edge)
                assert pname in _valid_params(s.components[src_idx]), (s.id, edge)


# --------------------------------------------------------------------------- #
# Landscape ↔ optfn coupling and the featured case
# --------------------------------------------------------------------------- #
def test_landscape_set_iff_optfn_category(specs: list[cases.CaseSpec]) -> None:
    """optfn cases carry a registered landscape + global hint; nothing else does."""
    for s in specs:
        match s.category:
            case "optfn":
                assert s.landscape in models.LANDSCAPE_REGISTRY, s.id
                assert s.solver_hint == "global", s.id
                assert s.recover is False, s.id
            case _:
                assert s.landscape is None, s.id


def test_exactly_one_featured_case_the_reality_tri_gaussian(
    specs: list[cases.CaseSpec], catalog: list[cases.BenchCase]
) -> None:
    """One featured case: the reality tri-Gaussian the peak panels assume (a/c/s)."""
    featured = [s for s in specs if s.featured]
    assert len(featured) == 1, [s.id for s in featured]
    f = featured[0]
    assert f.category == "reality"
    assert [c.model for c in f.components] == ["gaussian"] * 3
    assert cases.featured_case(catalog).id == f.id


def test_solver_meta_ids_unique_and_nonempty() -> None:
    ids = [m.id for m in cases.SOLVER_META]
    assert ids
    assert len(ids) == len(set(ids)), f"duplicate solver ids: {ids}"


# --------------------------------------------------------------------------- #
# Materialization: determinism, shapes, constraint semantics
# --------------------------------------------------------------------------- #
def test_build_specs_is_deterministic(specs: list[cases.CaseSpec]) -> None:
    assert cases.build_specs() == specs


def test_materialize_is_deterministic_per_spec(
    specs: list[cases.CaseSpec], catalog: list[cases.BenchCase]
) -> None:
    """materialize(spec) is a pure function of the spec (seeded by its id)."""
    for spec, built in zip(specs, catalog, strict=True):
        assert built.spec == spec
        again = cases.materialize(spec)
        assert np.array_equal(again.x, built.x), spec.id
        assert np.array_equal(again.y, built.y), spec.id
        assert again.comp_guess == built.comp_guess, spec.id


def test_materialized_data_shapes_and_finiteness(
    catalog: list[cases.BenchCase],
) -> None:
    """x/y are n_points-long finite arrays; guess mirrors truth structurally."""
    for c in catalog:
        assert c.x.shape == (c.spec.n_points,), c.id
        assert c.y.shape == (c.spec.n_points,), c.id
        assert np.isfinite(c.x).all(), c.id
        assert np.isfinite(c.y).all(), c.id
        assert len(c.comp_guess) == len(c.comp_true), c.id
        for guess, truth in zip(c.comp_guess, c.comp_true, strict=True):
            assert guess.model == truth.model, c.id


def test_fixed_params_guess_equals_truth(catalog: list[cases.BenchCase]) -> None:
    """Params named in fixed_params are never jittered — guess value == truth."""
    checked = 0
    for c in catalog:
        for node_id, pnames in c.spec.fixed_params.items():
            idx = int(node_id[1:])
            truth = c.comp_true[idx].to_params()
            guess = c.comp_guess[idx].to_params()
            for name in pnames:
                assert guess[name] == truth[name], (c.id, node_id, name)
                checked += 1
    assert checked > 0, "the fixed category must exercise this invariant"


def test_free_params_are_jittered_in_guess(catalog: list[cases.BenchCase]) -> None:
    """Non-landscape cases start from a perturbed guess, never from the truth."""
    for c in catalog:
        if c.spec.landscape is not None:
            continue
        guess = {
            f"p{i}.{k}": v
            for i, comp in enumerate(c.comp_guess)
            for k, v in comp.to_params().items()
        }
        assert guess != c.true_params, f"{c.id}: guess identical to truth"


def test_true_params_keys_are_dotted_node_params(
    catalog: list[cases.BenchCase],
) -> None:
    """true_params is keyed 'p{i}.{param}' over exactly the registry param names."""
    for c in catalog:
        expected = {
            f"p{i}.{name}"
            for i, comp in enumerate(c.comp_true)
            for name in models.get_model(comp.model).param_names
        }
        assert set(c.true_params) == expected, c.id
