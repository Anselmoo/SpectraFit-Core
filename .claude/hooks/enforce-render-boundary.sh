#!/usr/bin/env bash
set -euo pipefail

# Capture stdin before the heredoc consumes it.
_tmpf=$(mktemp)
trap 'rm -f "$_tmpf"' EXIT
cat > "$_tmpf"

python3 - <<PYEOF
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def allow() -> None:
    # Silent exit 0 = proceed. Emitting no stdout avoids hook-output
    # schema validation entirely (the safest "allow" contract).
    return


def block(reason: str) -> None:
    # Exit 2 blocks the tool call; stderr is surfaced back to Claude.
    print(reason, file=sys.stderr)
    raise SystemExit(2)


with open("$_tmpf", encoding="utf-8") as _fh:
    raw = _fh.read().strip()

if not raw:
    allow()
    raise SystemExit(0)

try:
    payload = json.loads(raw)
except json.JSONDecodeError:
    allow()
    raise SystemExit(0)

tool_name = payload.get("tool_name", "") if isinstance(payload, dict) else ""
tool_input = payload.get("tool_input", {}) if isinstance(payload, dict) else {}
path_value = (tool_input.get("file_path") or tool_input.get("path")) if isinstance(tool_input, dict) else None
if not isinstance(path_value, str):
    allow()
    raise SystemExit(0)

path = Path(path_value)
if path.suffix not in {".py", ".ts", ".tsx"}:
    allow()
    raise SystemExit(0)

normalized = path.as_posix()
is_backend = (
    normalized.startswith("python/oracles/")
) and path.suffix == ".py"
is_frontend = normalized.startswith("web/") and path.suffix in {".ts", ".tsx"}

if not (is_backend or is_frontend):
    allow()
    raise SystemExit(0)


def proposed_text() -> str | None:
    """The content that *will exist* after this tool call (PreToolUse runs
    before the write), so the guard catches violations being introduced —
    not the stale on-disk version."""
    content = tool_input.get("content")
    new_string = tool_input.get("new_string")
    if tool_name == "Write" and isinstance(content, str):
        return content
    if tool_name == "Edit" and isinstance(new_string, str):
        old_string = tool_input.get("old_string") or ""
        if path.exists():
            try:
                disk = path.read_text(encoding="utf-8")
            except OSError:
                return new_string
            return disk.replace(old_string, new_string) if old_string and old_string in disk else new_string
        return new_string
    return path.read_text(encoding="utf-8") if path.exists() else None


text = proposed_text()
if text is None:
    allow()
    raise SystemExit(0)

if "hook: allow-render-boundary-exception" in text:
    allow()
    raise SystemExit(0)

if is_backend:
    forbidden_backend_patterns: list[tuple[str, str]] = [
        (r"\bjinja2\b", "Do not reintroduce jinja2/template rendering in Python benchmark exporters."),
        (r"\b(?:Environment|FileSystemLoader|PackageLoader|Template)\s*\(", "Do not instantiate template engines in backend benchmark Python files."),
        (r"\brender_template\b", "Backend benchmark Python files must not perform template rendering."),
        (r"<style\b|</style>|<!DOCTYPE html>|<html\b", "Backend benchmark Python files must not embed HTML/CSS presentation markup."),
        (r"\btheme\s*=\s*[\"']|\bstylesheet\b|\bbackground-color\b|\bfont-family\b", "Keep report theming in frontend TSX/Tailwind, not Python exporters."),
    ]
    for pattern, message in forbidden_backend_patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            block(f"Frontend/backend boundary violation in {normalized}: {message}")

if is_frontend:
    forbidden_frontend_patterns: list[tuple[str, str]] = [
        (r"\bfrom\s+pydantic\b|\bBaseModel\b|\bmodel_validate(?:_json)?\b|\bValidationError\b", "Frontend TSX should not own backend Pydantic validation logic."),
        (r"python/oracles/|\bspectrafit_core\b", "Frontend TSX should not import Python backend internals directly."),
        (r"\bdef\s+\w+\s*\(", "Detected Python syntax in frontend TypeScript/TSX file."),
    ]
    for pattern, message in forbidden_frontend_patterns:
        if re.search(pattern, text):
            block(f"Frontend/backend boundary violation in {normalized}: {message}")

allow()
PYEOF
