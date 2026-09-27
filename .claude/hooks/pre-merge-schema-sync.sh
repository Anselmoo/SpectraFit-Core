#!/bin/bash
# [GIT PRE-COMMIT/PRE-PUSH] Wired in .pre-commit-config.yaml (id:
# pre-merge-schema-sync, stages: [pre-commit, pre-push]). It is NOT manual-only:
# the "MANUAL-ONLY / absent from CI and poe" note this header used to carry was
# stale in both directions — the hook was wired, and what it checked was not the
# thing its own name and CLAUDE.md promised. See the audit note at the bottom.

################################################################################
# Schema Sync Checker
#
# Purpose: enforce the CLAUDE.md contract —
#     "Python<->Rust JSON-boundary alignment is checked by pre-merge-schema-sync
#      — if you change ModelTypeStr or a serde-tagged struct, update the matching
#      Python side in the same commit."
#
#   Concretely: for every serde-tagged struct in crates/spectrafit-types/src/
#   types.rs that has a Pydantic mirror in python/spectrafit_core/, the set of
#   JSON *wire field names* must match exactly. Renaming a serde field (or its
#   `#[serde(rename = "...")]`) without renaming the Pydantic field is the
#   defect this gate exists to stop: both sides still compile, both still pass
#   their own unit tests, and the payload silently loses the field at runtime.
#
# Scope (deliberate, and deliberately narrow):
#   * IN  — wire field-name parity per paired struct/model, honouring
#           `#[serde(rename)]`, `#[serde(rename_all)]`, `#[serde(skip)]` and
#           Pydantic `serialization_alias=` / base-class inheritance;
#           plus completeness: a new serde struct with no registered pairing
#           fails rather than passing unnoticed.
#   * OUT — the ModelTypeStr <-> Python ModelType wire-string enumeration. That
#           is already pinned by tests/parity/test_schema_parity.py and by
#           .claude/hooks/enforce-modeltype-parity.sh; duplicating it here would
#           just be a second thing to keep in sync.
#   * OUT — type-level agreement (f64 vs float, Option vs | None, required vs
#           defaulted). Those diverge legitimately and often; claiming to check
#           them is how this file got into trouble the first time.
#
# Overrides (used by tests/meta/test_hook_enforcement.py to drive the gate
# against a fixture tree instead of mutating live source):
#   SCHEMA_SYNC_RUST_TYPES   path to the Rust types file
#   SCHEMA_SYNC_PYTHON_DIR   directory of Pydantic mirrors
#
# Exit codes:
#   0 = every paired struct's wire field names match
#   1 = drift detected, OR the gate could not actually run (missing file,
#       unparseable input, a pairing whose Rust struct or Python model is not
#       where it was declared to be). "Could not run" is a FAILURE here, never
#       a pass — an inert gate that reports PASS is worse than no gate.
#
# Audit note (2026-08-21, GOV-02): before this rewrite the gate read
# crates/spectrafit-types/src/lib.rs — a 21-line re-export shim with zero struct
# or enum definitions — so every Rust-side branch was INFO-only and the script
# exited 0 unconditionally. It reported "PASS: Schemas appear to be in sync"
# while checking nothing on the Rust side at all.
################################################################################

set -uo pipefail

# Resolve the repo root without depending on cwd being inside the worktree:
# a gate that silently mis-resolves its own root is how GOV-02 started.
if ! REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || [ -z "$REPO_ROOT" ]; then
    REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
fi
RUST_TYPES="${SCHEMA_SYNC_RUST_TYPES:-$REPO_ROOT/crates/spectrafit-types/src/types.rs}"
PYTHON_SCHEMAS="${SCHEMA_SYNC_PYTHON_DIR:-$REPO_ROOT/python/spectrafit_core}"

echo "[Schema Sync Checker] Validating Python<->Rust wire field parity..."
echo "[Schema Sync Checker]   rust:   $RUST_TYPES"
echo "[Schema Sync Checker]   python: $PYTHON_SCHEMAS"

if [ ! -f "$RUST_TYPES" ]; then
    echo "[Schema Sync Checker] FAIL: Rust types file not found: $RUST_TYPES"
    echo "  The gate cannot run, which is a failure — not a silent pass."
    exit 1
fi

if [ ! -d "$PYTHON_SCHEMAS" ]; then
    echo "[Schema Sync Checker] FAIL: Python schema dir not found: $PYTHON_SCHEMAS"
    echo "  The gate cannot run, which is a failure — not a silent pass."
    exit 1
fi

python3 - "$RUST_TYPES" "$PYTHON_SCHEMAS" <<'PYEOF'
"""Compare serde wire field names against their Pydantic mirrors.

Pure stdlib (ast + re): this runs as a pre-commit gate, so it must not need
the project venv, maturin, or a compiled extension.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# --- the pairing registry ---------------------------------------------------
# (Rust struct in types.rs, Pydantic model in python/spectrafit_core/**).
# Registry-over-map: adding a mirrored wire struct is one line here.
PAIRS: tuple[tuple[str, str], ...] = (
    ("ParameterSpec", "Parameter"),
    ("ParameterResultSpec", "ParameterResult"),
    ("ModelNodeSpec", "ModelNodeSpec"),
    ("ExprEdge", "ExprEdge"),
    ("FitGraphSpec", "FitGraph"),
    ("MeasurementSpec", "MeasurementData"),
    ("FitOptionsSpec", "FitOptions"),
    ("DatasetSliceSpec", "DatasetSlice"),
    ("FitResultSpec", "FitResult"),
)

# Serde structs that deliberately have no Pydantic mirror. Empty on purpose:
# every wire struct in types.rs is mirrored today. A new struct lands in the
# completeness check below and must be either paired above or excused here —
# it cannot slip through unnoticed.
RUST_ONLY: frozenset[str] = frozenset()

STRUCT_RE = re.compile(r"^pub struct ([A-Za-z_][A-Za-z0-9_]*)\s*\{")
FIELD_RE = re.compile(r"^\s{4}pub ([a-z_][a-z0-9_]*)\s*:")
ATTR_RE = re.compile(r"^\s*#\[")
RENAME_RE = re.compile(r'rename\s*=\s*"([^"]+)"')
RENAME_ALL_RE = re.compile(r'rename_all\s*=\s*"([^"]+)"')


def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(p.title() for p in rest)


RENAME_ALL = {
    "snake_case": lambda s: s,
    "camelCase": _camel,
}


class RustParseError(RuntimeError):
    """Raised when types.rs carries a serde attribute this gate cannot honour."""


def parse_rust(path: Path) -> dict[str, tuple[set[str], bool]]:
    """Map struct name -> (wire field names, derives Serialize/Deserialize)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    out: dict[str, tuple[set[str], bool]] = {}
    i = 0
    while i < len(lines):
        m = STRUCT_RE.match(lines[i])
        if m is None:
            i += 1
            continue
        name = m.group(1)
        # Look back over the attribute/doc block for derives and rename_all.
        j, preamble = i - 1, []
        while j >= 0 and (lines[j].startswith(("#[", "///", "//!", "//"))):
            preamble.append(lines[j])
            j -= 1
        head = "\n".join(reversed(preamble))
        serde = "Serialize" in head or "Deserialize" in head
        ra = RENAME_ALL_RE.search(head)
        if ra is not None and ra.group(1) not in RENAME_ALL:
            msg = f"{name}: unsupported #[serde(rename_all = {ra.group(1)!r})]"
            raise RustParseError(msg)
        case_fn = RENAME_ALL[ra.group(1)] if ra is not None else RENAME_ALL["snake_case"]

        fields: set[str] = set()
        attrs: list[str] = []
        i += 1
        while i < len(lines) and lines[i] != "}":
            line = lines[i]
            if ATTR_RE.match(line):
                attrs.append(line)
            else:
                fm = FIELD_RE.match(line)
                if fm is not None:
                    blob = " ".join(attrs)
                    if "skip" in blob and "skip_serializing_if" not in blob:
                        pass  # not on the wire at all
                    else:
                        rn = RENAME_RE.search(blob)
                        fields.add(rn.group(1) if rn else case_fn(fm.group(1)))
                    attrs = []
            i += 1
        out[name] = (fields, serde)
    return out


def _model_bodies(root: Path) -> dict[str, ast.ClassDef]:
    out: dict[str, ast.ClassDef] = {}
    for py in sorted(root.rglob("*.py")):
        tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                out.setdefault(node.name, node)
    return out


def _alias(node: ast.AnnAssign) -> str | None:
    call = node.value
    if not isinstance(call, ast.Call):
        return None
    for kw in call.keywords:
        if kw.arg == "serialization_alias" and isinstance(kw.value, ast.Constant):
            return str(kw.value.value)
    return None


def _own_fields(cls: ast.ClassDef) -> set[str]:
    fields: set[str] = set()
    for stmt in cls.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue
        name = stmt.target.id
        if name.startswith("_") or name == "model_config":
            continue
        ann = ast.unparse(stmt.annotation)
        if ann.startswith("ClassVar"):
            continue
        fields.add(_alias(stmt) or name)
    return fields


def parse_python(root: Path) -> dict[str, set[str]]:
    """Map Pydantic model name -> wire field names, base classes folded in."""
    bodies = _model_bodies(root)
    resolved: dict[str, set[str]] = {}

    def walk(name: str, seen: frozenset[str]) -> set[str]:
        if name in resolved:
            return resolved[name]
        cls = bodies[name]
        fields = _own_fields(cls)
        for base in cls.bases:
            bname = base.id if isinstance(base, ast.Name) else None
            if bname in bodies and bname not in seen:
                fields |= walk(bname, seen | {name})
        resolved[name] = fields
        return fields

    for name in bodies:
        walk(name, frozenset())
    return resolved


def main() -> int:
    rust_path, py_root = Path(sys.argv[1]), Path(sys.argv[2])
    try:
        rust = parse_rust(rust_path)
        python = parse_python(py_root)
    except (RustParseError, SyntaxError) as exc:
        print(f"VIOLATION: could not parse the schema sources: {exc}")
        return 1

    violations = 0

    # 1. The gate must be pointed at files that actually define the schemas.
    #    This is the GOV-02 guard: reading a re-export shim finds zero structs,
    #    which used to look exactly like "in sync".
    for rs, pm in PAIRS:
        if rs not in rust:
            print(f"VIOLATION: Rust struct '{rs}' is not defined in {rust_path}.")
            print("  Either it was renamed/removed (update PAIRS in this hook),")
            print("  or this gate is pointed at the wrong file and checks nothing.")
            violations += 1
        if pm not in python:
            print(f"VIOLATION: Pydantic model '{pm}' not found under {py_root}.")
            violations += 1

    # 2. Wire field-name parity per pairing.
    for rs, pm in PAIRS:
        if rs not in rust or pm not in python:
            continue
        rust_fields = rust[rs][0]
        py_fields = python[pm]
        only_rust = sorted(rust_fields - py_fields)
        only_py = sorted(py_fields - rust_fields)
        if only_rust or only_py:
            violations += 1
            print(f"VIOLATION: wire field drift between {rs} (Rust) and {pm} (Python).")
            if only_rust:
                print(f"  only in Rust   : {', '.join(only_rust)}")
            if only_py:
                print(f"  only in Python : {', '.join(only_py)}")
            print("  A serde field renamed on one side only silently drops that")
            print("  field from the JSON payload at runtime. Fix both sides in")
            print("  the same commit (CLAUDE.md, 'Schema sync').")

    # 3. Completeness: a new serde struct must be paired or explicitly excused.
    paired = {rs for rs, _ in PAIRS}
    for name, (_fields, serde) in sorted(rust.items()):
        if serde and name not in paired and name not in RUST_ONLY:
            violations += 1
            print(f"VIOLATION: serde struct '{name}' has no registered pairing.")
            print("  Add it to PAIRS (with its Pydantic mirror) or to RUST_ONLY")
            print("  in .claude/hooks/pre-merge-schema-sync.sh.")

    if violations:
        print(f"[Schema Sync Checker] FAIL: {violations} schema-sync violation(s).")
        return 1

    checked = ", ".join(f"{rs}<->{pm}" for rs, pm in PAIRS)
    print(f"[Schema Sync Checker] PASS: {len(PAIRS)} pairings in sync ({checked}).")
    return 0


sys.exit(main())
PYEOF
