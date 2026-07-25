#!/usr/bin/env python3
"""Cycle 8.5 — scripted re-audit of Rust ↔ Python binding coverage.

Two invariants the audit doc (`docs/rust_binding_audit.md`) pins:

1. **All PyO3 entrypoints** registered in `crates/spectrafit-core/src/lib.rs`
   (`m.add_function(wrap_pyfunction!(NAME, m)?)?`) appear in the audit's
   "PyO3 entrypoints" table.
2. **All `Solver::` enum variants** declared in
   `crates/spectrafit-solver/src/dispatch.rs` (the `enum Solver { ... }`
   block) appear in the audit's "Solver dispatch" table.

A new variant added in either crate without an audit entry triggers the
script's exit-1 — the same pattern as the contract-drift guard in CI
(`web/src/openapi.gen.ts` diff-exit-code at `.github/workflows/ci.yml`).

This is a *staticly-grep* audit, not a symbolic one (no rust-analyzer
required), so it runs in CI without extra deps.

Usage:
    python scripts/audit_bindings.py          # exit 1 on drift
    python scripts/audit_bindings.py --list   # print observed surface
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT_MD = ROOT / "docs" / "rust_binding_audit.md"
LIB_RS = ROOT / "crates" / "spectrafit-core" / "src" / "lib.rs"
DISPATCH_RS = ROOT / "crates" / "spectrafit-solver" / "src" / "dispatch.rs"


def _pyfunctions_in_pymodule() -> set[str]:
    """Names registered via `m.add_function(wrap_pyfunction!(NAME, m)?)?`.

    Matches the actual registration site (the `#[pymodule]` body) rather than
    every `#[pyfunction]` declaration — a declared-but-not-registered function
    is invisible from Python regardless of its annotation.
    """
    text = LIB_RS.read_text()
    return set(
        re.findall(r"wrap_pyfunction!\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,\s*m\s*\)", text)
    )


def _solver_variants() -> set[str]:
    """Variant names from the `enum Solver { ... }` block.

    Returns the bare variant identifiers (`Lm`, `LmLegacy`, `Trf`, …). Tuple
    variants (`Irls(WeightFn)`) are normalised to the leading identifier.
    """
    text = DISPATCH_RS.read_text()
    m = re.search(r"enum Solver\s*\{([^}]*)\}", text, re.DOTALL)
    if not m:
        return set()
    body = m.group(1)
    variants: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        ident = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", stripped)
        if ident:
            variants.add(ident.group(1))
    return variants


def _audit_doc_mentions(name: str) -> bool:
    """Does `name` appear in the audit doc as a bare identifier or table cell?

    Loose match (the audit uses snake-case in narrative text and CamelCase in
    code-fence tables) — we look for either form anywhere in the file.
    """
    text = AUDIT_MD.read_text()
    return name in text or _camel_to_snake(name) in text


def _camel_to_snake(name: str) -> str:
    """`LmLegacy` → `lm_legacy`; for docs that use Rust snake-case strings."""
    s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s1).lower()


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: audit bindings, emit a non-zero exit on undocumented surface."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the observed PyO3 + Solver surfaces and exit 0.",
    )
    args = parser.parse_args(argv)

    pyfunctions = _pyfunctions_in_pymodule()
    solvers = _solver_variants()

    if args.list:
        print("PyO3 entrypoints registered in `_core`:")
        for name in sorted(pyfunctions):
            print(f"  - {name}")
        print("\nSolver:: variants in dispatch.rs:")
        for name in sorted(solvers):
            print(f"  - {name}")
        return 0

    drift: list[str] = []
    for name in sorted(pyfunctions):
        if not _audit_doc_mentions(name):
            drift.append(
                f"PyO3 entrypoint `{name}` is registered but NOT mentioned in {AUDIT_MD.relative_to(ROOT)}"
            )
    for name in sorted(solvers):
        if not _audit_doc_mentions(name):
            drift.append(
                f"Solver::{name} variant is declared but NOT mentioned in {AUDIT_MD.relative_to(ROOT)}"
            )

    if drift:
        print("Rust binding audit drift detected:", file=sys.stderr)
        for line in drift:
            print(f"  • {line}", file=sys.stderr)
        print(
            f"\nRefresh {AUDIT_MD.relative_to(ROOT)} to add the new surface, "
            "then re-run this audit. See the doc's 'Maintenance' section.",
            file=sys.stderr,
        )
        return 1

    print(
        f"Rust binding audit clean: {len(pyfunctions)} PyO3 entrypoints + "
        f"{len(solvers)} Solver variants all documented."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
