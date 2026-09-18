"""Shape gate for the NIST StRD data modules.

Each module under ``python/oracles/nist_strd/`` is pure data. Its constants
belong in one Google-style ``Attributes:`` section on the module docstring,
not in scattered attribute docstrings — griffe parses the former into a
structured ``attributes`` section and the latter, when it begins with a blank
line, into undifferentiated text.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parents[2] / "python" / "oracles" / "nist_strd"


def _module_paths() -> list[Path]:
    return sorted(p for p in _PKG.glob("*.py") if p.name != "__init__.py")


def _attribute_docstrings(tree: ast.Module) -> list[str]:
    out: list[str] = []
    for prev, node in zip(tree.body, tree.body[1:], strict=False):
        is_assign = isinstance(prev, (ast.Assign, ast.AnnAssign))
        is_str = (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        )
        if is_assign and is_str:
            out.append(node.value.value)
    return out


def _extract_attribute_name(line: str) -> str | None:
    """Extract the attribute name from an Attributes: section entry.

    Accepts both bare names and type-annotated names:
    - NAME: description
    - NAME (type): description
    - NAME (dict[str, float]): description

    Returns the bare name, or None if the line does not match the pattern.
    """
    stripped = line.strip()
    match = re.match(r"^(?P<name>[A-Za-z_]\w*)\s*(\([^)]*\))?\s*:", stripped)
    return match.group("name") if match else None


def _public_constants(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        match node:
            case ast.AnnAssign(target=ast.Name(id=name)):
                names.add(name)
            case ast.Assign(targets=[ast.Name(id=name)]):
                names.add(name)
    return {n for n in names if not n.startswith("_")}


def test_attribute_name_parser_accepts_both_forms() -> None:
    """Bare and type-annotated Attributes entries both parse to the same name."""
    # Bare form
    assert _extract_attribute_name("    START1: NIST-published starting guess.") == "START1"
    # Type-annotated form
    assert (
        _extract_attribute_name("    START1 (dict[str, float]): NIST-published starting guess.")
        == "START1"
    )
    # Complex nested type
    assert (
        _extract_attribute_name("    DATA (dict[str, tuple[float, float]]): Nested tuple type.")
        == "DATA"
    )
    # With extra whitespace
    assert _extract_attribute_name("    N_OBS  (int) : Number of observations.") == "N_OBS"


@pytest.mark.parametrize("path", _module_paths(), ids=lambda p: p.stem)
def test_constants_are_documented_in_one_attributes_section(path: Path) -> None:
    """No scattered attribute docstrings; every public constant is in Attributes:."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert not _attribute_docstrings(tree), (
        f"{path.name}: {len(_attribute_docstrings(tree))} scattered attribute "
        "docstring(s) remain; merge them into the module docstring's Attributes: section"
    )
    doc = ast.get_docstring(tree) or ""
    assert "Attributes:" in doc, f"{path.name}: module docstring has no Attributes: section"
    documented = {
        name
        for line in doc.split("Attributes:", 1)[1].splitlines()
        if line.startswith("    ")
        and not line.startswith("        ")
        and (name := _extract_attribute_name(line)) is not None
    }
    missing = _public_constants(tree) - documented
    assert not missing, f"{path.name}: public constants missing from Attributes: {sorted(missing)}"
