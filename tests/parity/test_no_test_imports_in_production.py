"""Invariant: production code must never import from ``tests/``.

Dependency direction is one-way — ``tests/`` may import production
(``python/**``), never the reverse. A production module that imports a test-only
module (e.g. a fixture) breaks every consumer that runs without ``tests/`` on
the path: the ``build:report_html`` CI job runs with ``PYTHONPATH=python`` only,
so ``from tests.fixtures…`` there raises ``ModuleNotFoundError: No module named
'tests'`` and crashes ``run_audit``.

This test is the generalized enforcement (BPDD): it fails on the reported
instance AND every sibling, so the class — not just the sample — stays closed.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROD_ROOT = _REPO_ROOT / "python"

# Imports of test code from production. Matches `from tests …`, `import tests`,
# and any `tests.fixtures` reference.
_FORBIDDEN = (
    re.compile(r"^\s*from\s+tests\b", re.MULTILINE),
    re.compile(r"^\s*import\s+tests\b", re.MULTILINE),
    re.compile(r"\btests\.fixtures\b"),
)


def test_production_never_imports_from_tests() -> None:
    violations: list[str] = []
    for pyfile in sorted(_PROD_ROOT.rglob("*.py")):
        try:
            text = pyfile.read_text(encoding="utf-8")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(p.search(line) for p in _FORBIDDEN):
                rel = pyfile.relative_to(_REPO_ROOT)
                violations.append(f"  {rel}:{line_no}: {line.strip()}")

    assert not violations, (
        "production code (python/**) must NOT import from tests/ — the dependency "
        "direction is one-way (tests may import production, never the reverse). "
        "Relocate the imported module into production and update the import:\n"
        + "\n".join(violations)
    )
