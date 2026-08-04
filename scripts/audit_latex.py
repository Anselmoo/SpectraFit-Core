"""Audit docs/**/*.md for broken or drifted LaTeX math markup.

Checks, per file, after stripping fenced code blocks and inline code spans
(arithmatex never processes math inside either — a `$` there is inert, not a
delimiter):

1. Unbalanced ``$`` count outside code (an odd count means a delimiter is
   unterminated, or a literal ``$`` was meant as a dollar sign, not a
   fenced-code false negative).
2. A ``$...$``/``$$...$$`` span that contains a bare ``|`` while sitting
   inside a markdown table row — breaks the table, since pymdownx tables
   split cells on unescaped ``|`` before arithmatex ever sees the math.
3. A soft heuristic scan for plain-text formula notation (``A * exp(``,
   ``A·exp(``, ``^2``/``**2`` next to a known model-formula keyword) outside
   any ``$...$`` span — a sign of un-converted or duplicated-and-drifted
   math content (see the `architecture.md` "Built-in models" fix this script
   was written after: a hand-copied formula table had drifted back to plain
   text after `reference/models/index.md` moved to real LaTeX).

Usage: ``uv run python scripts/audit_latex.py`` (exits 1 if any hard issue
found; heuristic hits are reported but don't fail the run).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

DOCS_ROOT = Path(__file__).resolve().parent.parent / "docs"

FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
MATH_SPAN_RE = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$", re.DOTALL)
PLAIN_FORMULA_RE = re.compile(
    r"\b[Aa]\s*[*·]\s*exp\(|\b[Aa]\s*\*\s*\([^)]*\)\s*\^\s*\d"
)


def strip_code(text: str) -> str:
    """Blank out fenced code blocks and inline code spans, preserving line count."""
    text = FENCE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    text = INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), text)
    return text


def audit_file(path: Path) -> list[str]:
    """Return LaTeX/formula issues found in one markdown file."""
    issues: list[str] = []
    raw = path.read_text(encoding="utf-8")
    code_stripped = strip_code(raw)

    dollar_count = code_stripped.count("$")
    if dollar_count % 2 != 0:
        issues.append(
            f"{path}: odd count of unescaped '$' outside code ({dollar_count}) "
            "— a math delimiter is likely unterminated"
        )

    for lineno, line in enumerate(code_stripped.splitlines(), start=1):
        if not line.lstrip().startswith("|"):
            continue
        for match in MATH_SPAN_RE.finditer(line):
            if "|" in match.group(0):
                issues.append(
                    f"{path}:{lineno}: table-cell math span contains a bare "
                    f"'|' — breaks the table: {match.group(0)!r}"
                )

    for lineno, line in enumerate(code_stripped.splitlines(), start=1):
        # Skip content already inside a $...$/$$...$$ span on this line.
        line_no_math = MATH_SPAN_RE.sub("", line)
        if PLAIN_FORMULA_RE.search(line_no_math):
            issues.append(
                f"{path}:{lineno}: [heuristic] plain-text formula notation "
                f"outside any $...$ span — possibly un-converted or drifted "
                f"math: {line.strip()[:80]!r}"
            )

    return issues


def main() -> int:
    """Audit every docs/**/*.md file and print a summary; exit 1 on a hard issue."""
    all_issues: list[str] = []
    hard_issue = False
    for md_file in sorted(DOCS_ROOT.rglob("*.md")):
        issues = audit_file(md_file)
        for issue in issues:
            all_issues.append(issue)
            if "[heuristic]" not in issue:
                hard_issue = True

    if not all_issues:
        print(
            f"audit_latex: clean — no issues across {len(list(DOCS_ROOT.rglob('*.md')))} files"
        )
        return 0

    for issue in all_issues:
        print(issue)
    print(f"\naudit_latex: {len(all_issues)} finding(s)")
    return 1 if hard_issue else 0


if __name__ == "__main__":
    sys.exit(main())
