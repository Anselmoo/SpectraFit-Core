#!/usr/bin/env python3
"""Cycle 8.5+ — scripted re-audit of Rust <-> Python binding coverage.

Two invariants pinned by `scripts/binding_audit_notes.toml`:

1. **All PyO3 entrypoints** registered in `crates/spectrafit-core/src/lib.rs`
   (`m.add_function(wrap_pyfunction!(NAME, m)?)?`) have a one-line
   description under `[pyfunctions]` in the notes file.
2. **All `Solver::` enum variants** declared in
   `crates/spectrafit-solver/src/dispatch.rs` (the `enum Solver { ... }`
   block) have a one-line description under `[solver_variants]`.

The check is symmetric: a notes entry with no matching grepped name is
*also* drift (stale entry left behind after a binding was removed).

The default (no-flag) invocation is CI-facing and depends on nothing under
`docs/` — a docs-site reorg can never break this gate again. `docs/
reference/rust/binding-audit.md` is an optional, non-gated Markdown
rendering of the same data, regenerated on request via `--write` (see `poe
audit_bindings_regen`); CI never reads or diffs it.

This is a *statically-grep* audit, not a symbolic one (no rust-analyzer
required), so it runs in CI without extra deps.

Usage:
    python scripts/audit_bindings.py          # exit 1 on drift (CI gate)
    python scripts/audit_bindings.py --list   # print observed surface
    python scripts/audit_bindings.py --write  # regenerate docs/reference/rust/binding-audit.md
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AUDIT_MD = ROOT / "docs" / "reference" / "rust" / "binding-audit.md"
NOTES_TOML = ROOT / "scripts" / "binding_audit_notes.toml"
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


def _load_notes() -> dict[str, dict[str, str]]:
    """Load `scripts/binding_audit_notes.toml`, defaulting missing tables to `{}`."""
    if not NOTES_TOML.exists():
        return {"pyfunctions": {}, "solver_variants": {}}
    with NOTES_TOML.open("rb") as f:
        data = tomllib.load(f)
    return {
        "pyfunctions": data.get("pyfunctions", {}),
        "solver_variants": data.get("solver_variants", {}),
    }


def _check_drift(
    pyfunctions: set[str], solvers: set[str], notes: dict[str, dict[str, str]]
) -> list[str]:
    """Symmetric diff between grepped source names and the notes file's keys."""
    drift: list[str] = []

    for name in sorted(pyfunctions):
        if name not in notes["pyfunctions"]:
            drift.append(
                f"PyO3 entrypoint `{name}` is registered but has no description "
                f"under [pyfunctions] in {NOTES_TOML.relative_to(ROOT)}"
            )
    for name in sorted(notes["pyfunctions"]):
        if name not in pyfunctions:
            drift.append(
                f"[pyfunctions] entry `{name}` in {NOTES_TOML.relative_to(ROOT)} "
                "no longer matches any registered PyO3 entrypoint — remove it"
            )

    for name in sorted(solvers):
        if name not in notes["solver_variants"]:
            drift.append(
                f"Solver::{name} variant is declared but has no description "
                f"under [solver_variants] in {NOTES_TOML.relative_to(ROOT)}"
            )
    for name in sorted(notes["solver_variants"]):
        if name not in solvers:
            drift.append(
                f"[solver_variants] entry `{name}` in {NOTES_TOML.relative_to(ROOT)} "
                "no longer matches any Solver:: variant — remove it"
            )

    return drift


def _render_markdown(
    pyfunctions: set[str], solvers: set[str], notes: dict[str, dict[str, str]]
) -> str:
    """Deterministic Markdown rendering (sorted, no timestamps) for `--write`."""
    lines = [
        "---",
        "icon: lucide/list-checks",
        "---",
        "",
        "# Rust ↔ Python binding audit",
        "",
        (
            "Generated by `scripts/audit_bindings.py --write` from "
            "`scripts/binding_audit_notes.toml` + the grepped PyO3/Solver surface. "
            "This file is **not** read by CI — edit "
            "`scripts/binding_audit_notes.toml` and re-run "
            "`uv run poe audit_bindings_regen`, don't hand-edit this page."
        ),
        "",
        "## PyO3 entrypoints (`crates/spectrafit-core/src/lib.rs`)",
        "",
        "| Entrypoint | Description |",
        "| :--- | :--- |",
    ]
    for name in sorted(pyfunctions):
        lines.append(f"| `{name}` | {notes['pyfunctions'][name]} |")
    lines += [
        "",
        "## Solver dispatch (`crates/spectrafit-solver/src/dispatch.rs`)",
        "",
        "| Solver::Variant | Description |",
        "| :--- | :--- |",
    ]
    for name in sorted(solvers):
        lines.append(f"| `Solver::{name}` | {notes['solver_variants'][name]} |")
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: audit bindings, emit a non-zero exit on undocumented surface."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the observed PyO3 + Solver surfaces and exit 0.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help=f"Regenerate {AUDIT_MD.relative_to(ROOT)} (optional, non-gated) and exit.",
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

    notes = _load_notes()
    drift = _check_drift(pyfunctions, solvers, notes)

    if args.write:
        if drift:
            print(
                f"Cannot regenerate {AUDIT_MD.relative_to(ROOT)}: "
                f"{NOTES_TOML.relative_to(ROOT)} is out of sync with source.",
                file=sys.stderr,
            )
            for line in drift:
                print(f"  • {line}", file=sys.stderr)
            return 1
        AUDIT_MD.parent.mkdir(parents=True, exist_ok=True)
        AUDIT_MD.write_text(_render_markdown(pyfunctions, solvers, notes))
        print(f"Wrote {AUDIT_MD.relative_to(ROOT)}")
        return 0

    if drift:
        print("Rust binding audit drift detected:", file=sys.stderr)
        for line in drift:
            print(f"  • {line}", file=sys.stderr)
        print(
            f"\nUpdate {NOTES_TOML.relative_to(ROOT)} to add/remove the affected "
            "entry, then re-run this audit. Optionally refresh the human-readable "
            "doc with `uv run poe audit_bindings_regen`.",
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
