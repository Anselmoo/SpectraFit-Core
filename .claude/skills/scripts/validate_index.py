#!/usr/bin/env python3
"""Validate .claude/skills/INDEX.yaml.

Two layers of validation:

1. JSON-schema shape — every entry has name/stream/anchors/etc.
2. Anchor existence — every CLAUDE.md section header listed in
   `anchors.claude_md_sections` must exist verbatim in CLAUDE.md (case
   sensitive, leading `## ` or `### ` stripped). Every hook listed in
   `anchors.hooks` must exist as a real file under .claude/hooks/.

Exit codes:
  0 — registry is healthy.
  1 — schema violation, missing CLAUDE.md section, or missing hook file.

Usage:
  python .claude/skills/scripts/validate_index.py
  (run from repo root)
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _load_yaml(path: Path) -> dict:
    """Minimal YAML loader avoiding a pyyaml dependency in CI bootstrap.

    The index is intentionally simple — mappings, lists, strings, ints,
    bools, multi-line `|` blocks, no flow style. We try pyyaml first and
    fall back to ruamel/yaml if needed; if neither is available, surface
    the failure rather than silently degrade.
    """
    try:
        import yaml  # type: ignore
    except ImportError:  # pragma: no cover
        print(
            "validate_index: pyyaml not available. "
            "Install with `uv add --dev pyyaml` or `pip install pyyaml`.",
            file=sys.stderr,
        )
        sys.exit(2)
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def _validate_schema(index: dict, schema_path: Path) -> list[str]:
    """Return a list of human-readable schema violations (empty = ok)."""
    try:
        import jsonschema  # type: ignore
    except ImportError:
        # Without jsonschema, run a degraded shape check rather than
        # silently passing. Surface that the dev dependency is missing.
        print(
            "validate_index: jsonschema not available — running degraded checks. "
            "Install with `uv add --dev jsonschema` for full validation.",
            file=sys.stderr,
        )
        errs: list[str] = []
        if index.get("schema_version") != 1:
            errs.append("schema_version must be 1")
        if not isinstance(index.get("skills"), list) or not index["skills"]:
            errs.append("skills must be a non-empty list")
        return errs

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    return [
        f"{'/'.join(str(p) for p in err.path)}: {err.message}"
        for err in validator.iter_errors(index)
    ]


_HEADER_RE = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)


def _claude_md_sections(claude_md: Path) -> set[str]:
    if not claude_md.exists():
        return set()
    text = claude_md.read_text(encoding="utf-8")
    return {m.group(1).strip() for m in _HEADER_RE.finditer(text)}


def _validate_anchors(index: dict, repo_root: Path) -> list[str]:
    errs: list[str] = []
    sections = _claude_md_sections(repo_root / "CLAUDE.md")
    hooks_dir = repo_root / ".claude" / "hooks"

    for skill in index.get("skills", []):
        name = skill.get("name", "<unnamed>")
        anchors = skill.get("anchors", {})

        for header in anchors.get("claude_md_sections", []):
            if header not in sections:
                errs.append(
                    f"{name}: anchor section not found in CLAUDE.md: {header!r}"
                )

        for hook in anchors.get("hooks", []):
            if not (hooks_dir / hook).exists():
                errs.append(f"{name}: hook file missing: .claude/hooks/{hook}")

    return errs


def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    index_path = repo_root / ".claude" / "skills" / "INDEX.yaml"
    schema_path = repo_root / ".claude" / "skills" / "INDEX.schema.json"

    if not index_path.exists():
        print(f"validate_index: missing {index_path}", file=sys.stderr)
        return 1
    if not schema_path.exists():
        print(f"validate_index: missing {schema_path}", file=sys.stderr)
        return 1

    index = _load_yaml(index_path)

    schema_errs = _validate_schema(index, schema_path)
    anchor_errs = _validate_anchors(index, repo_root)

    if schema_errs:
        print("SCHEMA VIOLATIONS:", file=sys.stderr)
        for err in schema_errs:
            print(f"  - {err}", file=sys.stderr)
    if anchor_errs:
        print("ANCHOR VIOLATIONS:", file=sys.stderr)
        for err in anchor_errs:
            print(f"  - {err}", file=sys.stderr)

    if schema_errs or anchor_errs:
        return 1

    n_skills = len(index.get("skills", []))
    n_wires = len(index.get("inter_stream_wires", []))
    n_streams = len(index.get("streams", []))
    print(
        f"validate_index: ok — {n_skills} skills, {n_streams} streams, "
        f"{n_wires} inter-stream wires."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
