"""Guard: Bennett5 and MGH09 track convergence by the termination reason.

The NIST StRD scenario modules ``tests/scenario/nist_strd/test_bennett5.py`` and
``tests/scenario/nist_strd/test_mgh09.py`` each carry two
``xfail(strict=False)`` tests, one per NIST start, that track whether the LM
solver stops on a convergence test and recovers the certified parameters.

Since #93 ``FitResult.success`` is not a convergence signal. It is ``True`` only
when a convergence test or a ``no_improvement_possible`` stop ends the fit
**and** the end point passes the Gauss-Newton stationarity gate and the post-fit
guards: a convergence stop at a non-stationary end point reads
``success=False``, and a ``no_improvement_possible`` stop at a stationary end
point reads ``success=True``. The tracking therefore reads the termination
reason ``FitResult.message`` and requires it to be one of the keys a convergence
test produces on the ``solver="lm"`` path: the variants accepted by
``Termination::was_successful`` (``spectrafit-trust-region``) as mapped to
strings by ``faer_termination_str`` (``spectrafit-solver``), pinned here as
``CONVERGENCE_TERMINATIONS``. A message rewritten by a post-fit guard
(``diverged_off_domain (...)``, ``degenerate_fit (...)``) is not in the set.

**Method.** Each scenario module is parsed with :mod:`ast` and must satisfy
three conditions: no attribute access ``.success`` anywhere in the module; exactly
two tracking tests, i.e. ``test_*`` functions decorated with
``pytest.mark.xfail(strict=False, ...)``, each comparing ``<expr>.message`` by
membership ``in`` against the module constant ``_CONVERGENCE_TERMINATIONS``; and
that constant equal to ``CONVERGENCE_TERMINATIONS``. The checkers are pure
functions over source text, so a synthetic snippet proves that each condition
fails on the success-based form.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCENARIO_DIR = _REPO_ROOT / "tests" / "scenario" / "nist_strd"
_TRACKED_MODULES = ("test_bennett5.py", "test_mgh09.py")
_CONSTANT_NAME = "_CONVERGENCE_TERMINATIONS"

CONVERGENCE_TERMINATIONS: frozenset[str] = frozenset(
    {"converged_ftol", "converged_gtol", "converged_xtol", "residuals_zero"},
)

_SUCCESS_BASED_SNIPPET = """
import pytest

_CONVERGENCE_TERMINATIONS = frozenset({"converged_ftol"})


@pytest.mark.xfail(strict=False, reason="ill-conditioned")
def test_recovers_start1() -> None:
    result = fit()
    assert result.success is True, result.message


@pytest.mark.xfail(strict=False, reason="ill-conditioned")
def test_recovers_start2() -> None:
    result = fit()
    assert result.success, result.message
"""


def success_reads(source: str) -> list[int]:
    """Return the line numbers of every ``.success`` attribute access in *source*.

    Args:
        source (str): Python source text of a test module.

    Returns:
        list[int]: Sorted line numbers of ``ast.Attribute`` nodes with
            ``attr == "success"``; empty when the module never reads the flag.
    """
    return sorted(
        node.lineno
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Attribute) and node.attr == "success"
    )


def _is_nonstrict_xfail(decorator: ast.expr) -> bool:
    """Whether *decorator* is ``pytest.mark.xfail(..., strict=False, ...)``.

    Args:
        decorator (ast.expr): One entry of a function's ``decorator_list``.

    Returns:
        bool: ``True`` for a call of an attribute named ``xfail`` that passes the
            keyword ``strict`` with the constant ``False``.
    """
    match decorator:
        case ast.Call(func=ast.Attribute(attr="xfail"), keywords=keywords):
            return any(
                kw.arg == "strict"
                and isinstance(kw.value, ast.Constant)
                and kw.value.value is False
                for kw in keywords
            )
        case _:
            return False


def tracking_functions(source: str) -> list[ast.FunctionDef]:
    """Return the module-level ``test_*`` functions marked ``xfail(strict=False)``.

    Args:
        source (str): Python source text of a test module.

    Returns:
        list[ast.FunctionDef]: The convergence-tracking tests in source order.
    """
    return [
        node
        for node in ast.parse(source).body
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_")
        and any(_is_nonstrict_xfail(d) for d in node.decorator_list)
    ]


def reads_termination_reason(func: ast.FunctionDef) -> bool:
    """Whether *func* tests ``<expr>.message in _CONVERGENCE_TERMINATIONS``.

    Args:
        func (ast.FunctionDef): A convergence-tracking test function.

    Returns:
        bool: ``True`` if the body contains a membership comparison whose left
            operand is a ``.message`` attribute and whose single comparator is
            the module constant ``_CONVERGENCE_TERMINATIONS``.
    """
    for node in ast.walk(func):
        match node:
            case ast.Compare(
                left=ast.Attribute(attr="message"),
                ops=[ast.In()],
                comparators=[ast.Name(id=name)],
            ) if name == _CONSTANT_NAME:
                return True
            case _:
                continue
    return False


def convergence_constant(source: str) -> frozenset[str] | None:
    """Return the literal value of the module constant ``_CONVERGENCE_TERMINATIONS``.

    Args:
        source (str): Python source text of a test module.

    Returns:
        frozenset[str] | None: The string set passed to ``frozenset(...)`` in the
            module-level assignment, or ``None`` when the module defines no such
            constant in that form.
    """
    for node in ast.parse(source).body:
        match node:
            case (
                ast.AnnAssign(
                    target=ast.Name(id=name),
                    value=ast.Call(func=ast.Name(id="frozenset"), args=[arg]),
                )
                | ast.Assign(
                    targets=[ast.Name(id=name)],
                    value=ast.Call(func=ast.Name(id="frozenset"), args=[arg]),
                )
            ) if name == _CONSTANT_NAME:
                return frozenset(ast.literal_eval(arg))
            case _:
                continue
    return None


def _module_source(module: str) -> str:
    """Read one tracked scenario module from the checkout.

    Args:
        module (str): File name under ``tests/scenario/nist_strd/``.

    Returns:
        str: The module's source text.
    """
    return (_SCENARIO_DIR / module).read_text(encoding="utf-8")


@pytest.mark.parametrize("module", _TRACKED_MODULES)
def test_module_reads_no_success_flag(module: str) -> None:
    """The scenario module never reads ``FitResult.success``."""
    assert success_reads(_module_source(module)) == [], (
        f"{module} reads .success at lines {success_reads(_module_source(module))}; "
        "track convergence by result.message in _CONVERGENCE_TERMINATIONS instead"
    )


@pytest.mark.parametrize("module", _TRACKED_MODULES)
def test_tracking_functions_read_termination_reason(module: str) -> None:
    """Both non-strict xfail tests compare the termination reason to the convergence set."""
    functions = tracking_functions(_module_source(module))
    assert len(functions) == 2, (
        f"{module}: expected 2 xfail(strict=False) tracking tests, "
        f"found {[f.name for f in functions]}"
    )
    missing = [f.name for f in functions if not reads_termination_reason(f)]
    assert missing == [], f"{module}: no `.message in {_CONSTANT_NAME}` check in {missing}"


@pytest.mark.parametrize("module", _TRACKED_MODULES)
def test_convergence_constant_matches_lm_convergence_keys(module: str) -> None:
    """The module's convergence set equals the keys of the LM convergence tests."""
    assert convergence_constant(_module_source(module)) == CONVERGENCE_TERMINATIONS


def test_checkers_reject_success_based_tracking() -> None:
    """A success-based tracking snippet violates every condition of the guard."""
    functions = tracking_functions(_SUCCESS_BASED_SNIPPET)
    assert success_reads(_SUCCESS_BASED_SNIPPET) == [10, 16]
    assert [f.name for f in functions] == ["test_recovers_start1", "test_recovers_start2"]
    assert not any(reads_termination_reason(f) for f in functions)
    assert convergence_constant(_SUCCESS_BASED_SNIPPET) == frozenset({"converged_ftol"})
    assert convergence_constant(_SUCCESS_BASED_SNIPPET) != CONVERGENCE_TERMINATIONS


def test_checkers_accept_termination_based_tracking() -> None:
    """A termination-based tracking function passes the guard's checks."""
    source = (
        "import pytest\n"
        "_CONVERGENCE_TERMINATIONS: frozenset[str] = frozenset({'converged_xtol'})\n"
        "@pytest.mark.xfail(strict=False, reason='r')\n"
        "def test_recovers() -> None:\n"
        "    result = fit()\n"
        "    assert result.message in _CONVERGENCE_TERMINATIONS, result.message\n"
        "@pytest.mark.xfail(strict=True, reason='r')\n"
        "def test_strict() -> None:\n"
        "    pass\n"
    )
    functions = tracking_functions(source)
    assert [f.name for f in functions] == ["test_recovers"]
    assert reads_termination_reason(functions[0])
    assert success_reads(source) == []
    assert convergence_constant(source) == frozenset({"converged_xtol"})
