"""Doc-drift guard: the catalog markdown must stay in sync with the live registries.

``docs/reference/models/catalog-roadmap.md`` carries a human-readable
"Current implementation snapshot" of which kernels / optimization landscapes ship. That
prose has historically gone stale — claiming "16 kernels / 12 landscapes" and marking
already-shipped shapes as not-done — while ``MODEL_REGISTRY`` / ``LANDSCAPE_REGISTRY``
grew underneath it.

These tests are the guard that would have caught that staleness:

* every ``MODEL_REGISTRY`` key is named somewhere in the catalog,
* every ``LANDSCAPE_REGISTRY`` key is named somewhere in the catalog,
* the snapshot count lines equal ``len(MODEL_REGISTRY)`` / ``len(LANDSCAPE_REGISTRY)``.

Because that guard existed, those two numbers stayed correct while *every other*
count in ``docs/`` drifted unguarded — the wire-variant count (34 → 37), the
shape-factory count (33 → 36), the benchmark-case count (139 → 151), the roster of
kernels without an analytical Jacobian (6 → 11), and the solver roster (7 → 10).
The second half of this module extends the same mechanism to those claims, one
source of truth each:

* wire variants — the Rust ``model_manifest!`` macro, read through
  ``_core.model_type_wire_strings()``,
* shape factories — ``spectrafit_core.compose.__all__``,
* benchmark cases and categories — ``oracles.cases.CATEGORY_REGISTRY``,
* kernels on a finite-difference Jacobian — the ``impl Model for`` blocks in
  ``crates/spectrafit-models/src/``,
* solvers — the ``enum Solver`` in ``crates/spectrafit-solver/src/dispatch.rs``.

Every expected value below is *derived* from one of those sources. Hard-coding it
here would only move the drift from the markdown into the test.

Parsing is by substring / regex (not exact table layout) so ordinary edits to the
markdown (reordering rows, rewording notes) do not break the guard — only a genuine
drift between the documented set/count and the code does.
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

from oracles.cases import CATEGORY_REGISTRY
from oracles.models import LANDSCAPE_REGISTRY, MODEL_REGISTRY

_ROOT = Path(__file__).resolve().parents[2]
_CATALOG = _ROOT / "docs" / "reference" / "models" / "catalog-roadmap.md"


def _catalog_text() -> str:
    assert _CATALOG.exists(), f"catalog doc missing: {_CATALOG}"
    return _CATALOG.read_text(encoding="utf-8")


def _doc(relative: str) -> str:
    """Read a repo-relative documentation/source file, asserting it still exists."""
    path = _ROOT / relative
    assert path.exists(), f"documented path moved or was deleted: {relative}"
    return path.read_text(encoding="utf-8")


def _count(text: str, pattern: str, where: str) -> int:
    """Extract the single integer captured by *pattern* from *text*."""
    match = re.search(pattern, text)
    assert match, f"could not find the {where} count line (pattern {pattern!r})"
    return int(match.group(1))


def _named_tokens(text: str) -> set[str]:
    """All snake_case identifiers mentioned anywhere in the catalog markdown."""
    return set(re.findall(r"[A-Za-z][A-Za-z0-9_]*", text))


def test_every_model_registry_key_is_named_in_catalog() -> None:
    """Each registered kernel key must appear (named) in the catalog doc."""
    tokens = _named_tokens(_catalog_text())
    missing = sorted(k for k in MODEL_REGISTRY if k not in tokens)
    assert not missing, (
        f"docs/reference/models/catalog-roadmap.md does not name these MODEL_REGISTRY kernels: {missing}. "
        "Add them (mark ✅) and update the snapshot count."
    )


def test_every_landscape_registry_key_is_named_in_catalog() -> None:
    """Each registered optimization-landscape key must appear in the catalog doc."""
    tokens = _named_tokens(_catalog_text())
    missing = sorted(k for k in LANDSCAPE_REGISTRY if k not in tokens)
    assert not missing, (
        f"docs/reference/models/catalog-roadmap.md does not name these LANDSCAPE_REGISTRY landscapes: {missing}. "
        "Add them (mark ✅) and update the snapshot count."
    )


def test_snapshot_kernel_count_matches_registry() -> None:
    """The '<N> peak/background kernels' snapshot line must equal len(MODEL_REGISTRY)."""
    text = _catalog_text()
    m = re.search(r"\*\*(\d+)\s+peak/background kernels", text)
    assert m, "could not find the '**<N> peak/background kernels**' snapshot line"
    documented = int(m.group(1))
    assert documented == len(MODEL_REGISTRY), (
        f"snapshot says {documented} kernels but MODEL_REGISTRY has {len(MODEL_REGISTRY)}; "
        "update the 'Current implementation snapshot' count in docs/reference/models/catalog-roadmap.md"
    )


def test_snapshot_landscape_count_matches_registry() -> None:
    """The '<N> optimization landscapes' snapshot line must equal len(LANDSCAPE_REGISTRY)."""
    text = _catalog_text()
    m = re.search(r"\*\*(\d+)\s+optimization landscapes", text)
    assert m, "could not find the '**<N> optimization landscapes**' snapshot line"
    documented = int(m.group(1))
    assert documented == len(LANDSCAPE_REGISTRY), (
        f"snapshot says {documented} landscapes but LANDSCAPE_REGISTRY has "
        f"{len(LANDSCAPE_REGISTRY)}; update the snapshot count in docs/reference/models/catalog-roadmap.md"
    )


# --------------------------------------------------------------------------------------
# Wire variants — source of truth: the Rust `model_manifest!` macro, exported at runtime
# as `_core.model_type_wire_strings()` (the same handle `tests/parity` pins the Python
# `ModelType` enum against).
# --------------------------------------------------------------------------------------

_WIRE_VARIANT_SITES = (
    # (documentation file, regex capturing the documented variant count)
    ("docs/contributor-guide/architecture.md", r"(\d+) wire variants as of"),
    ("docs/reference/rust/overview.md", r"the full (\d+)-kernel catalog"),
    ("docs/glossary.md", r"macro's (\d+) canonical"),
    ("docs/reference/models/index.md", r"wire strings for all (\d+) models in spectrafit-core"),
    ("docs/reference/models/index.md", r"src/types\.rs` — (\d+) wire variants"),
    ("docs/reference/models/index.md", r"\(all (\d+) variants below\)"),
    ("docs/why-spectrafit-core.md", r"eleven of the \*\*(\d+)\*\* Rust kernels registered in"),
)


def _wire_strings() -> set[str]:
    """The canonical wire strings, straight from the Rust manifest."""
    core = importlib.import_module("spectrafit_core._core")
    return set(json.loads(core.model_type_wire_strings()))


def test_documented_wire_variant_counts_match_the_manifest() -> None:
    """Every page quoting a wire-variant count must quote `len(ModelTypeStr::ALL)`."""
    expected = len(_wire_strings())
    for relative, pattern in _WIRE_VARIANT_SITES:
        documented = _count(_doc(relative), pattern, f"wire-variant count in {relative}")
        assert documented == expected, (
            f"{relative} says {documented} wire variants but the `model_manifest!` macro "
            f"exports {expected}; update the prose (this is the count that drifted 34 -> 37)"
        )


def test_model_reference_has_a_row_per_wire_string() -> None:
    """`docs/reference/models/index.md` claims to mirror the manifest — hold it to that."""
    page = _doc("docs/reference/models/index.md")
    rows = set(re.findall(r"^\| `([a-z0-9_]+)`", page, re.MULTILINE))
    expected = _wire_strings()
    assert not expected - rows, (
        "docs/reference/models/index.md is missing a table row for these wire strings: "
        f"{sorted(expected - rows)}"
    )
    assert not rows - expected, (
        "docs/reference/models/index.md documents wire strings the manifest does not export: "
        f"{sorted(rows - expected)}"
    )


# --------------------------------------------------------------------------------------
# Shape factories — source of truth: `spectrafit_core.compose.__all__` minus the two
# non-factory exports (`compose` itself and its builder).
# --------------------------------------------------------------------------------------

_SHAPE_FACTORY_SITES = (
    ("docs/reference/python/core-api.md", r"The (\d+) shape-factory functions"),
    ("docs/reference/python/shape-factories.md", r"The (\d+) shape-factory functions"),
    ("docs/reference/python/shape-factories.md", r"exposes (\d+) shape-factory functions"),
)

_NOT_A_SHAPE_FACTORY = frozenset({"ComposeBuilder", "compose"})


def _shape_factories() -> set[str]:
    """Public shape-factory names exported by `spectrafit_core.compose`."""
    compose_module = importlib.import_module("spectrafit_core.compose")
    return set(compose_module.__all__) - _NOT_A_SHAPE_FACTORY


def test_documented_shape_factory_counts_match_the_module() -> None:
    """Every page quoting a shape-factory count must quote the module's own export set."""
    expected = len(_shape_factories())
    for relative, pattern in _SHAPE_FACTORY_SITES:
        documented = _count(_doc(relative), pattern, f"shape-factory count in {relative}")
        assert documented == expected, (
            f"{relative} says {documented} shape factories but `spectrafit_core.compose` "
            f"exports {expected}; update the prose (this is the count that drifted 33 -> 36)"
        )


def test_shape_factory_page_documents_every_factory() -> None:
    """The shape-factory page must carry a mkdocstrings entry for each exported factory."""
    page = _doc("docs/reference/python/shape-factories.md")
    documented = set(re.findall(r"::: spectrafit_core\.compose\.(\w+)", page))
    missing = sorted(_shape_factories() - documented)
    assert not missing, (
        "docs/reference/python/shape-factories.md has no `::: spectrafit_core.compose.<name>` "
        f"entry for these factories: {missing}"
    )


# --------------------------------------------------------------------------------------
# Benchmark suite — source of truth: `oracles.cases.CATEGORY_REGISTRY`, the single record
# per category that `CATEGORY_COUNTS`/`CATEGORY_LABELS`/`PREFIX` are all projected from.
# --------------------------------------------------------------------------------------

_CASE_COUNT_SITES = (
    ("docs/reference/models/catalog-roadmap.md", r"\*\*Catalog:\*\* (\d+) diversity-driven cases"),
    ("docs/contributor-guide/architecture.md", r"run_suite \(all (\d+)\)"),
)


def test_documented_case_counts_match_the_category_registry() -> None:
    """Every page quoting a suite size must quote the sum of the registry's `count`s."""
    expected = sum(category.count for category in CATEGORY_REGISTRY.values())
    for relative, pattern in _CASE_COUNT_SITES:
        documented = _count(_doc(relative), pattern, f"benchmark-case count in {relative}")
        assert documented == expected, (
            f"{relative} says {documented} benchmark cases but CATEGORY_REGISTRY sums to "
            f"{expected}; update the prose (this is the count that drifted 139 -> 151)"
        )


def test_catalog_names_every_suite_category() -> None:
    """The catalog's case line must enumerate every registered category, not a stale subset."""
    match = re.search(
        r"\*\*Catalog:\*\* \d+ diversity-driven cases.*?(?=\n\n|\n##)",
        _catalog_text(),
        re.DOTALL,
    )
    assert match, "could not find the '**Catalog:** <N> diversity-driven cases' line"
    line = match.group(0)
    named = set(re.findall(r"[A-Za-z][A-Za-z0-9_]*", line))
    missing = sorted(cid for cid in CATEGORY_REGISTRY if cid not in named)
    assert not missing, (
        "the catalog's case line does not name these CATEGORY_REGISTRY categories: "
        f"{missing} (the `fixed` and `tied` categories were omitted for exactly this reason)"
    )


# --------------------------------------------------------------------------------------
# Analytical Jacobians — source of truth: the `impl Model for` blocks under
# `crates/spectrafit-models/src/`. A kernel is "FD" when its `jacobian` override is the
# hand-written central-difference loop (`f_plus`/`f_minus`) rather than a closed form.
# --------------------------------------------------------------------------------------

_MODELS_SRC = _ROOT / "crates" / "spectrafit-models" / "src"


def _balanced_body(text: str, open_brace: int) -> str:
    """Return the `{...}` block starting at *open_brace*, brace-matched."""
    depth = 0
    for index in range(open_brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace : index + 1]
    msg = "unbalanced braces in Rust source"
    raise AssertionError(msg)


def _kebab_to_snake(name: str) -> str:
    """`SplitPearson7` -> `split_pearson7` — the Rust struct to wire-string convention."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _finite_difference_kernels() -> set[str]:
    """Kernels whose `Model::jacobian` is a hand-written finite-difference loop."""
    fd: set[str] = set()
    for source in sorted(_MODELS_SRC.glob("*.rs")):
        text = source.read_text(encoding="utf-8")
        for impl in re.finditer(r"impl\s+Model\s+for\s+([A-Za-z0-9_]+)\s*\{", text):
            body = _balanced_body(text, impl.end() - 1)
            jacobian = re.search(r"fn jacobian\b", body)
            # No override at all also means finite differences (the trait default).
            if jacobian is None:
                fd.add(_kebab_to_snake(impl.group(1)))
                continue
            override = _balanced_body(body, body.index("{", jacobian.end()))
            if "f_plus" in override or "f_minus" in override:
                fd.add(_kebab_to_snake(impl.group(1)))
    assert fd, "found no `impl Model for` blocks — did crates/spectrafit-models move?"
    return fd


def test_finite_difference_kernel_names_are_real_wire_strings() -> None:
    """Pin the struct-name -> wire-string convention the FD roster is derived through."""
    unknown = sorted(_finite_difference_kernels() - _wire_strings())
    assert not unknown, (
        "these finite-difference kernels do not map onto a manifest wire string: "
        f"{unknown}; the snake_case convention assumed by this guard no longer holds"
    )


def test_architecture_lists_every_finite_difference_kernel() -> None:
    """The `Model` trait sketch must name exactly the kernels still on FD Jacobians."""
    text = _doc("docs/contributor-guide/architecture.md")
    match = re.search(
        r"override with an analytical formula; (\d+) currently don't \((.*?)— each",
        text,
        re.DOTALL,
    )
    assert match, "could not find the 'N currently don't (...)' line in the Model trait sketch"
    expected = _finite_difference_kernels()
    documented_count = int(match.group(1))
    documented = set(re.findall(r"[a-z][a-z0-9_]*", match.group(2)))
    assert documented_count == len(expected), (
        f"architecture.md says {documented_count} kernels lack an analytical Jacobian but "
        f"crates/spectrafit-models has {len(expected)}; update the prose "
        "(this is the count that drifted 6 -> 11)"
    )
    assert not expected - documented, (
        f"architecture.md does not name these finite-difference kernels: {sorted(expected - documented)}"
    )
    assert not documented - expected, (
        "architecture.md names these as finite-difference, but they now have an analytical "
        f"Jacobian: {sorted(documented - expected)}"
    )


def test_why_spectrafit_core_lists_every_finite_difference_kernel() -> None:
    """`docs/why-spectrafit-core.md`'s "eleven exceptions" list must name exactly the FD roster."""
    text = _doc("docs/why-spectrafit-core.md")
    match = re.search(r"eleven exceptions — (.*?) — each hand-roll", text, re.DOTALL)
    assert match, "could not find the 'eleven exceptions — (...) — each hand-roll' line"
    expected = _finite_difference_kernels()
    documented = set(re.findall(r"[a-z][a-z0-9_]*", match.group(1)))
    assert not expected - documented, (
        "docs/why-spectrafit-core.md does not name these finite-difference kernels: "
        f"{sorted(expected - documented)}"
    )
    assert not documented - expected, (
        "docs/why-spectrafit-core.md names these as finite-difference, but they now have an "
        f"analytical Jacobian: {sorted(documented - expected)}"
    )


# --------------------------------------------------------------------------------------
# Solver roster — source of truth: `enum Solver` in crates/spectrafit-solver/src/dispatch.rs,
# which its own doc comment calls "the *one place* that answers 'which solvers exist'".
# --------------------------------------------------------------------------------------

_SOLVER_ROSTER_SITES = (
    "docs/contributor-guide/architecture.md",
    "docs/explanation/solver-selection.md",
    "docs/reference/rust/overview.md",
)


def _solver_wire_names() -> set[str]:
    """Canonical solver wire strings, kebab-cased from the `Solver` enum's variants."""
    dispatch = _doc("crates/spectrafit-solver/src/dispatch.rs")
    body = _balanced_body(dispatch, dispatch.index("{", dispatch.index("enum Solver")))
    variants = re.findall(r"^\s{4}([A-Z][A-Za-z0-9]*)[\(,]", body, re.MULTILINE)
    assert variants, "could not parse any `Solver` variants out of dispatch.rs"
    return {_kebab_to_snake(variant).replace("_", "-") for variant in variants}


def test_solver_roster_pages_name_every_solver() -> None:
    """No page may present a solver roster that silently omits a `Solver` variant."""
    expected = _solver_wire_names()
    for relative in _SOLVER_ROSTER_SITES:
        documented = set(re.findall(r"`([a-z][a-z0-9-]*)`", _doc(relative)))
        missing = sorted(expected - documented)
        assert not missing, (
            f"{relative} presents a solver roster that omits {missing}; "
            "dogleg/newton-cg/auto went missing this way before"
        )
