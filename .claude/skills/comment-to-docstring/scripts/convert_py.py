#!/usr/bin/env python3
"""Safely promote leading Python comment blocks to real docstrings."""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_COMMENT = re.compile(r"^(?P<indent>[ \t]*)#(?P<text>.*?)(?P<newline>\n?)$")
_DECLARATION = re.compile(r"^(?P<indent>[ \t]*)(?P<header>(?:async[ \t]+)?(?:def|class)\b.*)$")


@dataclass(frozen=True)
class Block:
    start: int
    end: int
    indent: str
    text: tuple[str, ...]


@dataclass(frozen=True)
class Conversion:
    start: int
    end: int
    replacement: tuple[str, ...]
    owner: str


def _comment_blocks(lines: list[str]) -> list[Block]:
    blocks: list[Block] = []
    index = 0
    while index < len(lines):
        match = _COMMENT.match(lines[index])
        if match is None:
            index += 1
            continue
        start = index
        indent = match.group("indent")
        text: list[str] = []
        while index < len(lines):
            current = _COMMENT.match(lines[index])
            if current is None or current.group("indent") != indent:
                break
            value = current.group("text")
            text.append(value[1:] if value.startswith(" ") else value)
            index += 1
        blocks.append(Block(start, index, indent, tuple(text)))
    return blocks


def _string_literal(node: ast.AST) -> bool:
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def _docstring_span(node: ast.AST) -> tuple[int, int] | None:
    body = getattr(node, "body", [])
    if not body or not _string_literal(body[0]):
        return None
    first = cast(ast.Expr, body[0])
    start = first.lineno - 1
    end = getattr(first, "end_lineno", first.lineno)
    return start, end


def _quote(text: tuple[str, ...], indent: str) -> tuple[str, ...]:
    # Triple-single quotes avoid changing the common double-quoted prose style;
    # switch delimiters when the content itself contains triple single quotes.
    delimiter = '\"\"\"' if any("'''" in line for line in text) else "'''"
    result = [f"{indent}{delimiter}\n"]
    result.extend(f"{indent}{line}\n" for line in text)
    result.append(f"{indent}{delimiter}\n")
    return tuple(result)


def convert_source(source: str, *, replace_existing: bool = False) -> tuple[str, dict[str, object]]:
    """Return transformed source and a machine-readable conversion report."""
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        raise ValueError(f"input is not valid Python: {error}") from error

    lines = source.splitlines(keepends=True)
    blocks = _comment_blocks(lines)
    nodes: list[tuple[ast.AST, str]] = [(tree, "module")]
    nodes.extend((node, "function" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "class") for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
    conversions: list[Conversion] = []
    skipped: list[dict[str, object]] = []

    for block in blocks:
        next_index = block.end
        while next_index < len(lines) and not lines[next_index].strip():
            next_index += 1
        next_line = lines[next_index] if next_index < len(lines) else ""
        owner: tuple[ast.AST, str] | None = None
        if block.start == 0 and next_index < len(lines):
            owner = (tree, "module")
        elif next_index < len(lines):
            if declaration := _DECLARATION.match(next_line):
                indent = declaration.group("indent")
                for node, kind in nodes[1:]:
                    if getattr(node, "lineno", -1) - 1 == next_index and " " * getattr(node, "col_offset", 0) == indent:
                        owner = (node, kind)
                        break
            if owner is None:
                for node, kind in nodes[1:]:
                    node_line = getattr(node, "lineno", -1) - 1
                    body_indent = " " * (getattr(node, "col_offset", 0) + 4)
                    if block.start == node_line + 1 and block.indent == body_indent:
                        owner = (node, kind)
                        break
        if owner is None:
            skipped.append({"start_line": block.start + 1, "end_line": block.end, "reason": "not module- or declaration-leading"})
            continue

        node, kind = owner
        replacement = _quote(block.text, block.indent)
        span = _docstring_span(node)
        if span is not None and not replace_existing:
            skipped.append({"start_line": block.start + 1, "end_line": block.end, "reason": "existing docstring preserved"})
            continue
        match span:
            case (old_start, old_end):
                if kind == "module":
                    conversions.append(Conversion(block.start, old_end, replacement, kind))
                else:
                    body_indent = lines[old_start][: len(lines[old_start]) - len(lines[old_start].lstrip())]
                    conversions.extend(
                        [
                            Conversion(block.start, block.end, (), kind),
                            Conversion(old_start, old_end, _quote(block.text, body_indent), kind),
                        ]
                    )
            case None:
                if kind == "module":
                    conversions.append(Conversion(block.start, block.end, replacement, kind))
                else:
                    node_line = getattr(node, "lineno", next_index + 1) - 1
                    body_indent = " " * (getattr(node, "col_offset", 0) + 4)
                    conversions.extend(
                        [
                            Conversion(block.start, block.end, (), kind),
                            Conversion(node_line + 1, node_line + 1, _quote(block.text, body_indent), kind),
                        ]
                    )

    output = lines[:]
    for conversion in sorted(conversions, key=lambda item: item.start, reverse=True):
        output[conversion.start : conversion.end] = list(conversion.replacement)
    transformed = "".join(output)
    try:
        ast.parse(transformed)
    except SyntaxError as error:
        raise ValueError(f"conversion produced invalid Python: {error}") from error
    return transformed, {"converted": [{"start_line": c.start + 1, "end_line": c.end, "owner": c.owner} for c in conversions], "skipped": skipped}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--apply", action="store_true", help="write the validated transformation")
    parser.add_argument("--dry-run", action="store_true", help="print a unified diff (default)")
    parser.add_argument("--replace-existing", action="store_true")
    parser.add_argument("--check", action="store_true", help="exit 1 when a safe conversion is available")
    parser.add_argument("--json-report", action="store_true")
    args = parser.parse_args(argv)

    original = args.path.read_text(encoding="utf-8")
    transformed, report = convert_source(original, replace_existing=args.replace_existing)
    if args.json_report:
        print(json.dumps(report, indent=2))
    if args.check:
        return 1 if report["converted"] else 0
    if args.apply:
        args.path.write_text(transformed, encoding="utf-8")
    else:
        sys.stdout.writelines(difflib.unified_diff(original.splitlines(keepends=True), transformed.splitlines(keepends=True), fromfile=str(args.path), tofile=f"{args.path} (docstrings)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
