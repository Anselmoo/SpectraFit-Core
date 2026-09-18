"""Panic boundary of the PyO3 entrypoints.

A Rust panic that crosses the PyO3 boundary surfaces in Python as
``pyo3_runtime.PanicException`` — a ``BaseException`` subclass that slips past
every ``except Exception`` handler in the Python layer.  ``crates/
spectrafit-core/src/lib.rs`` therefore wraps each solver-invoking entrypoint in
its ``guard`` helper (``std::panic::catch_unwind`` -> ``PyValueError``), so the
``Raises: ValueError`` contract advertised by ``_core.pyi`` holds for panics as
well as for validation errors.

Until 2026-09-08 that guard covered only the three JSON entrypoints; the two
array entrypoints — which are the ones ``spectrafit_core.fit`` and
``spectrafit_core.fit_fast`` actually call — were unguarded.  The source-level
test below is the regression guard for exactly that gap: it fails if a
solver-invoking ``#[pyfunction]`` is added or edited without the boundary.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_LIB_RS = _REPO_ROOT / "crates" / "spectrafit-core" / "src" / "lib.rs"

# Entrypoints that reach the solver / graph evaluator and must therefore sit
# inside the `guard` panic boundary.
_MUST_BE_GUARDED = frozenset(
    {
        "fit",
        "fit_arrays",
        "fit_arrays_numpy",
        "evaluate",
        "evaluate_components",
    },
)

# Entrypoints that are pure Rust-side enumeration with no user-supplied input
# and no kernel invocation, so they carry no panic surface to guard.
_NO_PANIC_SURFACE = frozenset({"model_type_wire_strings"})

# Mirrors the signature match in `.claude/hooks/pre-merge-pyO3.sh`: a bare
# ``^fn`` dropped every qualified binding (``pub fn``, ``pub(crate) fn``,
# ``async``/``unsafe``/``const``/``extern`` fns) from the roster, so adding one
# would have silently evaded ``test_pyfunction_roster_is_accounted_for``
# instead of forcing a guarded/no-panic-surface decision. Keep the two in step.
_FN_RE = re.compile(
    r"^[ \t]*(?:(?:pub(?:[ \t]*\([^)]*\))?|async|unsafe|const|extern[^ \n]*)[ \t]+)*"
    r"fn[ \t]+(?P<name>\w+)",
    re.MULTILINE,
)

# Matches a bare ``#[pyfunction]`` or an argument-taking
# ``#[pyfunction(signature = ...)]`` marker. Mirrors the widened marker
# regex in `.claude/hooks/pre-merge-pyO3.sh`: a plain ``"#[pyfunction]" in
# text`` substring check silently dropped every pyfunction that took
# attribute arguments from the roster.
_PYFUNCTION_MARKER_RE = re.compile(r"#\[pyfunction[\](]")


def _pyfunction_bodies(source: str) -> dict[str, str]:
    """Map each ``#[pyfunction]``-annotated free function name to its body text.

    The attribute block and the ``fn`` line are always contiguous (no blank
    line between them) in ``lib.rs``, so the paragraph immediately preceding a
    ``fn`` is enough to decide whether it is a PyO3 entrypoint.
    """
    bodies: dict[str, str] = {}
    for match in _FN_RE.finditer(source):
        preceding_paragraph = source[: match.start()].rsplit("\n\n", 1)[-1]
        if not _PYFUNCTION_MARKER_RE.search(preceding_paragraph):
            continue
        end = source.find("\n}\n", match.end())
        bodies[match.group("name")] = source[match.start() : end]
    return bodies


@pytest.fixture(scope="module")
def pyfunction_bodies() -> dict[str, str]:
    """Parse ``crates/spectrafit-core/src/lib.rs`` once per module."""
    if not _LIB_RS.is_file():
        pytest.skip(f"crate source not available at {_LIB_RS}")
    return _pyfunction_bodies(_LIB_RS.read_text(encoding="utf-8"))


def test_pyfunction_roster_is_accounted_for(pyfunction_bodies: dict[str, str]) -> None:
    """Every ``#[pyfunction]`` is classified, so a new binding forces a decision."""
    assert set(pyfunction_bodies) == _MUST_BE_GUARDED | _NO_PANIC_SURFACE


@pytest.mark.parametrize("name", sorted(_MUST_BE_GUARDED))
def test_solver_entrypoints_sit_inside_the_panic_boundary(
    name: str,
    pyfunction_bodies: dict[str, str],
) -> None:
    """Each solver-invoking entrypoint wraps its body in ``guard(...)``.

    ``fit_arrays`` and ``fit_arrays_numpy`` assert unwind safety explicitly
    because they capture PyO3 handles; ``guard(`` is the invariant either way.
    """
    body = pyfunction_bodies[name]
    assert "guard(" in body, f"{name} is not wrapped in the `guard` panic boundary"


@pytest.mark.skip(
    reason=(
        "No Python-reachable Rust panic is known on the fit_arrays paths: the "
        "kernel arity preconditions documented in spectrafit-models' `Model` "
        "trait are validated at graph-compile time (spectrafit-graph::compiler), "
        "the flat-buffer reshape in split_array_datasets uses checked `get(..)` "
        "slicing, and the one explicit `panic!` outside test modules "
        "(crates/spectrafit-builder/src/lib.rs) is a Rust-only builder helper "
        "with no PyO3 binding — every other `panic!` in the tree lives inside a "
        "`#[cfg(test)]` module. The six remaining non-test `.unwrap()`/`.expect(` "
        "call sites are spectrafit-solver/src/global.rs:359, "
        "spectrafit-graph/src/compiler.rs:257,269 and "
        "spectrafit-graph/src/expr.rs:318,324,492; four of those "
        "(global.rs:359, compiler.rs:257/269, expr.rs:492) are genuine panic "
        "risks guarded by an adjacent `// INVARIANT:` comment naming the "
        "structural guarantee that rules out the failure branch, while the "
        "other two (expr.rs:318,324) are calls to the expression parser's own "
        "`Result`-returning `expect` helper — unrelated to `Option`/"
        "`Result::expect` — which already propagates via `?`, so they carry no "
        "panic risk to guard. The guard is defence-in-depth for future kernels; "
        "the source-level tests above are what pin it. Un-skip and supply the "
        "input if a reachable panic is ever found."
    ),
)
def test_fit_arrays_maps_a_rust_panic_to_valueerror() -> None:
    """A panicking Rust input must reach Python as ``ValueError``."""
    raise AssertionError("no known panicking input — see the skip reason")
