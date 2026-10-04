"""Scripts under ``reproducibility/`` must resolve the repository root correctly.

The figure scripts were moved into ``reproducibility/figures/``, one directory
shallower than their previous location, without adjusting their ``parents[N]``
index, so three of them looked for the repository one directory above it.
Nothing failed loudly: ``nist_difficulty_tiers()`` returned an empty dict,
``fig_nist_catalogue.py`` labelled every dataset "Lower", and
``fig_architecture.py`` exited with "no crate manifests". These tests pin the
behaviour that was lost, plus a static guard over every ``parents[N]`` in the
directory so the next move cannot repeat it.
"""

from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from oracles.audit.nist import _RECIPES

REPO_ROOT = Path(__file__).resolve().parents[2]
REPRODUCIBILITY = REPO_ROOT / "reproducibility"
FIGURES = REPRODUCIBILITY / "figures"


def _load(stem: str) -> ModuleType:
    """Import a figure script by path, without running its ``__main__`` block."""
    spec = importlib.util.spec_from_file_location(f"_repro_{stem}", FIGURES / f"{stem}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_nist_difficulty_tiers_cover_every_implemented_dataset() -> None:
    """Every dataset the audit implements has a NIST difficulty tier, and nothing else does."""
    tiers = _load("extract_bench_summary").nist_difficulty_tiers()
    roster = {recipe.name.lower() for recipe in _RECIPES}
    assert set(tiers) == roster, (
        f"missing tiers: {sorted(roster - set(tiers))}; unexpected: {sorted(set(tiers) - roster)}"
    )
    assert len(tiers) == 22, f"expected the 22 implemented NIST StRD datasets, got {len(tiers)}"
    assert set(tiers.values()) <= {"Lower", "Average", "Higher"}


def test_fig_architecture_finds_the_crates() -> None:
    """The architecture figure counts crate manifests under the repository's own ``crates/``."""
    module = _load("fig_architecture")
    assert module.REPO == REPO_ROOT
    assert sorted((module.REPO / "crates").glob("*/Cargo.toml")), "no crate manifests found"


class _Unresolved(Exception):
    pass


def _evaluate(node: ast.expr, script: Path, assignments: dict[str, ast.expr]) -> Path:
    """Statically evaluate the path idioms the scripts use to locate themselves.

    Understands ``__file__``, ``Path(...)``, ``.resolve()``, ``.parent``,
    ``.parents[N]`` and module-level names bound to such expressions. Anything
    else raises ``_Unresolved`` so the test fails instead of silently skipping it.
    """
    match node:
        case ast.Name(id="__file__"):
            return script
        case ast.Name(id=name) if name in assignments:
            return _evaluate(assignments[name], script, assignments)
        case ast.Call(func=ast.Name(id="Path"), args=[arg]):
            return _evaluate(arg, script, assignments)
        case ast.Call(func=ast.Attribute(value=value, attr="resolve"), args=[]):
            return _evaluate(value, script, assignments).resolve()
        case ast.Attribute(value=value, attr="parent"):
            return _evaluate(value, script, assignments).parent
        case ast.Subscript(
            value=ast.Attribute(value=value, attr="parents"),
            slice=ast.Constant(value=int(n)),
        ):
            return _evaluate(value, script, assignments).parents[n]
        case _:
            raise _Unresolved(ast.unparse(node))


def _parents_subscripts() -> list[object]:  # pytest.param(...) values
    found = []
    for script in sorted(REPRODUCIBILITY.rglob("*.py")):
        tree = ast.parse(script.read_text(encoding="utf-8"))
        assignments = {
            target.id: stmt.value
            for stmt in tree.body
            if isinstance(stmt, ast.Assign)
            for target in stmt.targets
            if isinstance(target, ast.Name)
        }
        found += [
            pytest.param(script, node, assignments, id=f"{script.name}:{node.lineno}")
            for node in ast.walk(tree)
            if isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Attribute)
            and node.value.attr == "parents"
        ]
    return found


@pytest.mark.parametrize(("script", "node", "assignments"), _parents_subscripts())
def test_parents_index_stays_inside_the_repository(
    script: Path,
    node: ast.Subscript,
    assignments: dict[str, ast.expr],
) -> None:
    """Every ``parents[N]`` in ``reproducibility/`` resolves to the repository root or below it."""
    try:
        target = _evaluate(node, script.resolve(), assignments)
    except _Unresolved as exc:
        msg = f"{script.name}:{node.lineno}: cannot resolve `{exc}` statically"
        raise AssertionError(msg) from exc
    assert target == REPO_ROOT or REPO_ROOT in target.parents, (
        f"{script.name}:{node.lineno}: `{ast.unparse(node)}` resolves to {target}, "
        f"outside the repository {REPO_ROOT}"
    )
