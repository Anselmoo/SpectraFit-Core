r"""Audit the documentation and the manuscript for broken or drifted LaTeX math.

Checks, per file, after stripping fenced code blocks and inline code spans
(arithmatex never processes math inside either — a `$` there is inert, not a
delimiter):

1. Unbalanced ``$`` count outside code (an odd count means a delimiter is
   unterminated, or a literal ``$`` was meant as a dollar sign, not a
   fenced-code false negative).
2. A ``$...$``/``$$...$$`` span that contains a bare ``|`` while sitting
   inside a markdown table row — breaks the table, since pymdownx tables
   split cells on unescaped ``|`` before arithmatex ever sees the math.
3. An **empty-base** script span — ``$_{2,3}$`` or ``$^-$``, where the base of
   the subscript sits outside the math. This is invalid LaTeX; pandoc rescues
   it by inserting U+200B as the base, and Word then draws that empty slot as
   a placeholder box floating away from the word it belongs to. Write the
   whole token as one span with a real base (``$[\\mathrm{FeCl}_4]^-$``), or —
   for chemistry and other purely typographic scripts — use the sub/superscript
   marks in rule 4 instead of math at all.
4. An unpaired ``^`` or ``~`` outside code and outside a ``[^note]`` footnote
   reference. The docx reader runs ``gfm+subscript+superscript``, so those two
   characters now carry meaning: ``d^5^`` is a superscript run and ``~4~`` a
   subscript one. A lone ``^`` — a literal ``r^2`` that was never converted —
   either swallows text to the next caret or survives into Word as a raw ASCII
   caret beside a properly typeset equation.
5. A soft heuristic scan for plain-text formula notation (``A * exp(``,
   ``A·exp(``, ``^2``/``**2`` next to a known model-formula keyword) outside
   any ``$...$`` span — a sign of un-converted or duplicated-and-drifted
   math content (see the `architecture.md` "Built-in models" fix this script
   was written after: a hand-copied formula table had drifted back to plain
   text after `reference/models/index.md` moved to real LaTeX).
6. A soft heuristic scan for notation that should have been converted and was
   not: a bare oxidation state (``Fe3+``), a bare orbital occupancy (``d5``),
   or ``sigma``/``chi`` standing alone as a word where the symbol is meant.

Rules 1, 2 and 5 apply everywhere. Rules 3, 4 and 6 are **manuscript-only**,
because they describe how pandoc's docx writer behaves and the documentation
site does not go through it: `docs/` is rendered by Zensical with arithmatex,
where a display block spans lines, a lone ``~`` means "approximately", and
`sigma` is the name of a keyword argument rather than a symbol standing in for
one. Applying the Word rules there would report hundreds of non-defects and
train the reader to ignore the audit.

Covers ``docs/**/*.md``, the manuscript's ``sections/*.md``, and the caption and
alt-text fields of ``manuscript-state.json``. The manuscript was outside this
audit until 2026-08-18, which is how it reached a full draft carrying no math
markup at all -- every formula was plain text, and pandoc therefore emitted no
OMML, so Word showed running text where the venue expects equations. The state
file stayed outside it one revision longer, which is how Figure 3's caption kept
a plain ``(Fe3+, d5)`` sitting next to a correctly marked-up ``[FeCl$_4$]$^-$``
in the same sentence.

**Snippet-include resolution (mode B).** ``docs/**/*.md`` pages may pull in
prose from outside ``docs/`` via pymdownx.snippets' ``--8<-- "<path>"``
directive (e.g. ``docs/limitations.md`` is an 8-line stub whose body is
``--8<-- "LIMITATIONS.md"``). Any such page was a blind spot: the file walk
above only ever looks under ``DOCS_ROOT``, so the root ``LIMITATIONS.md`` (and
``SECURITY.md``, ``CHANGELOG.md``, ``CODE_OF_CONDUCT.md`` -- anything included
the same way) rendered on a gated docs page while sitting outside the gate.
``audited_files()`` now parses every ``--8<--`` directive under ``docs/``,
resolves it against the same ``base_path`` list Zensical reads from
``zensical.toml``'s ``[markdown_extensions.pymdownx.snippets]`` table, and adds
the resolved file to the audited set whenever it is itself markdown (``.md``).
Non-markdown snippet targets (the gallery's ``fitting.py``-style code-block
includes) are left out: this audit's markdown rules -- table-cell math, ``$``
balance, plain-formula heuristics -- assume markdown structure and would
misfire on Python source; those files are Python and, if they carry docstring
LaTeX violations, are a candidate for the Python pass below once/if they move
under ``PYTHON_ROOT`` (they currently sit under ``docs/tutorials/gallery`` and
are out of scope for both passes -- a known, documented residual gap, not
silently swallowed).

**Python docstring/Field(description=...) pass (mode A), report-only for now.**
CLAUDE.md states: "Math notation in Python docstrings is real LaTeX, never a
hand-typed unicode/ASCII approximation -- write ``$\\chi^2$``, ``$\\pm$``,
``$\\kappa(J)$``, not χ², ±, κ(J)." Nothing enforced that rule: this module's
file walk covered zero ``.py`` files, and ``pyproject.toml`` ignores
RUF001/RUF002/RUF003 (ambiguous-unicode), the one mechanical proxy ruff offers.
``audit_python_file()`` walks the AST of every file under ``PYTHON_ROOT``,
extracts every module/class/function docstring (the ``ast.Expr(Constant(str))``
that is a definition's first statement, mirroring what ``ast.get_docstring``
recognizes) and every ``Field(description=...)`` string-constant keyword
argument, and flags any character from ``UNICODE_MATH_GLYPHS``.

*Glyph boundary.* An initial sweep of ``python/**/*.py`` found roughly 64
unicode sites outside code, of which about 21 carry an unambiguous math glyph
(a Greek letter, a scripted digit, or an analysis/order operator) and the rest
are prose punctuation (arrows guiding the reader, an "x" written as "×" in a
casual aside) where treating the character as *math notation gone wrong* is
genuinely arguable. This module resolves that boundary in favor of the named,
mechanically unambiguous set: the full Greek alphabet (upper- and lower-case --
in a scientific-computing docstring a bare Greek letter is never an English
word, unlike ``sigma``/``chi`` spelled out, which rule 6 above already
special-cases for prose reasons), Unicode super-/subscript digits, and a small
set of analysis operators (``± ≤ ≥ ≠ ≈ ∞ √ ∑ ∫ ∂ ∇ ‖ ·``). It deliberately
excludes ``×`` and ``→``: both read as ordinary prose in this codebase's
docstrings ("A → B" as a data-flow arrow, "3× faster" as a multiplier) far
more often than as math notation, so including them by default would train
readers to ignore the audit, exactly the failure mode rule 5's docstring
warns about. The set is a module-level constant (``UNICODE_MATH_GLYPHS``)
precisely so that boundary can be revisited without touching the walker.

Usage: ``uv run python scripts/audit_latex.py`` (exits 1 if any hard issue
found; heuristic hits are reported but don't fail the run). The markdown
passes (modes covered by rules 1-6) run unconditionally, unchanged from
before. The Python pass (mode A) is **blocking** as of 2026-08-21: it runs
unconditionally and its findings flip the exit code, exactly like markdown
rules 1/2. It was promoted once the three contract modules that carried the
last known violations (``python/oracles/bench_contract.py``,
``python/oracles/trust_ledger.py``, ``python/oracles/audit/nist.py``) were
converted to LaTeX and ``poe contract_regen`` re-synced the OpenAPI goldens.
``--python`` is now redundant but kept, so the pass can still be run alone.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
DOCS_ROOT = _REPO / "docs"
MANUSCRIPT_ROOT = _REPO / "manuscript" / "draft" / "sections"
MANUSCRIPT_STATE = _REPO / "manuscript" / "draft" / "manuscript-state.json"
PYTHON_ROOT = _REPO / "python"
ZENSICAL_CONFIG = _REPO / "zensical.toml"

# Blocking as of 2026-08-21 (GOV-01). With this True, run_python_pass below
# is unconditional and its findings count toward the hard_issue exit-1 gate,
# exactly like markdown rules 1/2. Promoted only after the three contract
# modules (bench_contract.py, trust_ledger.py, audit/nist.py) were converted
# and `poe contract_regen` re-synced the goldens -- the tree was verified at
# 0 findings across 118 files first. No pyproject.toml or
# pre-commit-config.yaml edit was needed: both already invoke this script.
# Setting this back to False downgrades the pass to report-only.
PYTHON_LATEX_AUDIT_BLOCKING = True

SNIPPET_RE = re.compile(r'--8<--\s*"([^"]+)"')


def _snippet_base_paths() -> list[Path]:
    """Resolve pymdownx.snippets' ``base_path`` list from zensical.toml.

    Falls back to the documented default (``[".", "docs/tutorials/gallery"]``)
    if the config file is missing or doesn't parse -- this audit degrades to
    "use the known default" rather than crashing on an unrelated config typo.
    """
    default = [_REPO, DOCS_ROOT / "tutorials" / "gallery"]
    if not ZENSICAL_CONFIG.exists():
        return default
    try:
        config = tomllib.loads(ZENSICAL_CONFIG.read_text(encoding="utf-8"))
        raw = (
            config.get("markdown_extensions", {})
            .get("pymdownx", {})
            .get("snippets", {})
            .get("base_path")
        )
    except (tomllib.TOMLDecodeError, OSError):
        return default
    if not raw:
        return default
    return [(_REPO / entry).resolve() for entry in raw]


def _snippet_path_candidates(raw: str) -> list[str]:
    """A snippet directive's argument, and its section-stripped form.

    pymdownx.snippets allows ``"path:section"`` to include a named region
    (see the gallery's ``fitting.py:data``-style includes). POSIX paths in
    this repo never contain a literal ``:``, so splitting on the last one is
    unambiguous; the untouched string is tried first in case a path really
    has no section suffix.
    """
    candidates = [raw]
    if ":" in raw:
        candidates.append(raw.rsplit(":", 1)[0])
    return candidates


def resolve_snippet_targets(md_root: Path) -> list[Path]:
    """Every file pulled into ``md_root``'s pages via a ``--8<--`` directive.

    Resolves each directive against the snippet ``base_path`` list, the same
    order Zensical itself checks (first match wins). Only markdown targets
    are returned -- see the module docstring's "Snippet-include resolution"
    section for why non-markdown targets (Python code-block includes) are
    out of scope for this pass.
    """
    base_paths = _snippet_base_paths()
    resolved: list[Path] = []
    for md_file in sorted(md_root.rglob("*.md")):
        text = md_file.read_text(encoding="utf-8")
        for match in SNIPPET_RE.finditer(text):
            for candidate in _snippet_path_candidates(match.group(1)):
                for base in base_paths:
                    target = (base / candidate).resolve()
                    if target.is_file():
                        if target.suffix == ".md":
                            resolved.append(target)
                        break
                else:
                    continue
                break
    return resolved


def audited_files() -> list[Path]:
    """Every markdown file this audit covers, docs and manuscript alike.

    Includes files pulled in via pymdownx.snippets ``--8<--`` includes even
    when they live outside ``docs/`` (e.g. the root ``LIMITATIONS.md``,
    rendered through ``docs/limitations.md`` -- see NEW-2 in the module
    docstring).
    """
    direct = sorted(DOCS_ROOT.rglob("*.md")) + sorted(MANUSCRIPT_ROOT.glob("*.md"))
    snippet_targets = resolve_snippet_targets(DOCS_ROOT)
    return sorted(set(direct) | set(snippet_targets))


FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
MATH_SPAN_RE = re.compile(r"\$\$.*?\$\$|\$[^$\n]+\$", re.DOTALL)
PLAIN_FORMULA_RE = re.compile(
    r"\b[Aa]\s*[*·]\s*exp\(|\b[Aa]\s*\*\s*\([^)]*\)\s*\^\s*\d",
)

# Rule 3. A span whose first character is a script operator has no base.
EMPTY_BASE_RE = re.compile(r"\$[_^]")

# Rule 4. What legitimately carries a caret or a tilde, and so is not an
# unpaired one: a footnote reference or definition, and a paired sub/superscript
# mark. Marks may not contain whitespace, which is what keeps a stray caret in
# running prose from pairing with one three sentences away.
FOOTNOTE_RE = re.compile(r"\[\^[\w-]+\]:?")
SCRIPT_MARK_RE = re.compile(r"\^[^\s^]+\^|~[^\s~]+~")

# Rule 6. Notation the conversion is meant to have caught.
UNCONVERTED = (
    (re.compile(r"\b(?:Fe|Mn|Cu|Ni|Co|Cr)\d[+-]"), "bare oxidation state"),
    (re.compile(r"(?<![\w^])d[56](?![\w^])"), "bare orbital occupancy"),
    (re.compile(r"(?<![\w.`])(?:sigma|chi)(?![\w(])"), "symbol spelled as a word"),
)


def strip_code(text: str) -> str:
    """Blank out fenced code blocks and inline code spans, preserving line count."""
    text = FENCE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    return INLINE_CODE_RE.sub(lambda m: " " * len(m.group(0)), text)


def unpaired_marks(line: str) -> str:
    """Return the caret/tilde characters left once every legal use is removed."""
    rest = MATH_SPAN_RE.sub("", line)
    rest = FOOTNOTE_RE.sub("", rest)
    rest = SCRIPT_MARK_RE.sub("", rest)
    return "".join(c for c in rest if c in "^~")


def audit_text(
    label: str,
    raw: str,
    *,
    tables: bool = True,
    docx_path: bool = False,
) -> list[str]:
    """Return LaTeX/formula issues found in one body of markdown-ish text.

    ``docx_path`` turns on the three rules that only mean anything for text
    pandoc will convert to Word: empty-base scripts, unpaired sub/superscript
    marks, and notation that should have been converted and was not.
    """
    issues: list[str] = []
    code_stripped = strip_code(raw)

    dollar_count = code_stripped.count("$")
    if dollar_count % 2 != 0:
        issues.append(
            f"{label}: odd count of unescaped '$' outside code ({dollar_count}) "
            "— a math delimiter is likely unterminated",
        )

    for lineno, line in enumerate(code_stripped.splitlines(), start=1):
        if tables and line.lstrip().startswith("|"):
            for match in MATH_SPAN_RE.finditer(line):
                if "|" in match.group(0):
                    issues.append(
                        f"{label}:{lineno}: table-cell math span contains a bare "
                        f"'|' — breaks the table: {match.group(0)!r}",
                    )

        if docx_path:
            issues += _docx_path_issues(label, lineno, line)

        line_no_math = MATH_SPAN_RE.sub("", line)
        if PLAIN_FORMULA_RE.search(line_no_math):
            issues.append(
                f"{label}:{lineno}: [heuristic] plain-text formula notation "
                f"outside any $...$ span — possibly un-converted or drifted "
                f"math: {line.strip()[:80]!r}",
            )

    return issues


def _docx_path_issues(label: str, lineno: int, line: str) -> list[str]:
    """Rules that describe pandoc's docx writer, so manuscript text only."""
    issues: list[str] = []

    for match in EMPTY_BASE_RE.finditer(line):
        issues.append(
            f"{label}:{lineno}: math span with no base — pandoc emits a "
            f"U+200B placeholder and Word draws an empty box: "
            f"{line[match.start() : match.start() + 24]!r}",
        )

    stray = unpaired_marks(line)
    if stray:
        issues.append(
            f"{label}:{lineno}: unpaired {sorted(set(stray))} outside code — "
            f"the docx reader treats these as sub/superscript marks: "
            f"{line.strip()[:80]!r}",
        )

    line_no_math = MATH_SPAN_RE.sub("", line)
    for pattern, why in UNCONVERTED:
        found = pattern.search(line_no_math)
        if found:
            issues.append(
                f"{label}:{lineno}: [heuristic] {why} ({found.group(0)!r}) "
                f"— convert it, or the docx sets it as running text beside "
                f"the same quantity properly typeset: {line.strip()[:80]!r}",
            )

    return issues


def audit_file(path: Path) -> list[str]:
    """Return LaTeX/formula issues found in one markdown file."""
    return audit_text(
        str(path),
        path.read_text(encoding="utf-8"),
        docx_path=path.is_relative_to(MANUSCRIPT_ROOT),
    )


STATE_TEXT_FIELDS = ("caption", "alt_text")


def audit_state() -> list[str]:
    """Audit the caption and alt-text fields the renderer injects into the body.

    These strings never pass through a markdown file, so the file walk above
    cannot see them — yet the renderer drops them straight into MANUSCRIPT.md,
    where pandoc treats them exactly like authored prose.
    """
    if not MANUSCRIPT_STATE.exists():
        return []
    state = json.loads(MANUSCRIPT_STATE.read_text(encoding="utf-8"))
    issues: list[str] = []
    for group in ("figures", "tables", "listings", "algorithms"):
        for item in state.get(group, []):
            for field in STATE_TEXT_FIELDS:
                text = item.get(field)
                if not isinstance(text, str):
                    continue
                label = f"manuscript-state.json:{group}[{item.get('id')}].{field}"
                issues += audit_text(label, text, tables=False, docx_path=True)
    return issues


# ---------------------------------------------------------------------------
# Mode A: Python docstring / Field(description=...) unicode-math-glyph pass.
# See the module docstring's "Python docstring/Field(description=...) pass"
# section for the glyph-boundary rationale.
# ---------------------------------------------------------------------------

_GREEK = "".join(chr(c) for c in range(0x0391, 0x03CA) if chr(c).isalpha())
_SUPERSCRIPTS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_SUBSCRIPTS = "₀₁₂₃₄₅₆₇₈₉"
_OPERATORS = "±≤≥≠≈∞√∑∫∂∇‖·"

#: Characters this pass treats as "should have been real LaTeX" per
#: CLAUDE.md's docstring rule. Deliberately excludes ``×`` and ``→`` — see
#: the module docstring for why those stayed out of the default. Kept as a
#: module-level constant so the boundary can be revisited independently of
#: the walker that uses it.
UNICODE_MATH_GLYPHS = frozenset(_GREEK + _SUPERSCRIPTS + _SUBSCRIPTS + _OPERATORS)

_DOCTEST_PROMPT_RE = re.compile(r"^\s*>>>")


def strip_docstring_examples(text: str) -> str:
    """Blank out fenced code blocks and doctest blocks, preserving line count.

    Mirrors ``strip_code``'s contract (same line count in and out) so glyph
    offsets computed against the stripped text still map onto the original
    source lines. A doctest block starts at a ``>>>`` line and absorbs every
    following non-blank line (continuations and expected output) until the
    next blank line ends it.
    """
    text = FENCE_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)
    out: list[str] = []
    in_doctest = False
    for line in text.splitlines():
        if not in_doctest and _DOCTEST_PROMPT_RE.match(line):
            in_doctest = True
            out.append("")
            continue
        if in_doctest:
            if line.strip() == "":
                in_doctest = False
                out.append(line)
            else:
                out.append("")
            continue
        out.append(line)
    return "\n".join(out)


def _string_glyph_findings(label: str, value: str, lineno: int, col_offset: int) -> list[str]:
    """Scan one raw string literal for banned unicode math glyphs.

    ``lineno``/``col_offset`` are the AST position of the *start* of the
    string literal; columns on lines after the first are reported relative
    to that line's own start (0-based), not the source column of the
    literal's opening quote, since only the first line shares that origin.
    """
    issues: list[str] = []
    cleaned = strip_docstring_examples(value)
    for i, line in enumerate(cleaned.splitlines()):
        line_no = lineno + i
        col_base = col_offset if i == 0 else 0
        for j, ch in enumerate(line):
            if ch in UNICODE_MATH_GLYPHS:
                issues.append(
                    f"{label}:{line_no}:{col_base + j}: unicode math glyph "
                    f"{ch!r} — CLAUDE.md requires real LaTeX in Python "
                    f"docstrings/Field descriptions, not a hand-typed "
                    f"unicode approximation: {line.strip()[:80]!r}",
                )
    return issues


def _docstring_constant(
    node: ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef,
) -> ast.Constant | None:
    """The node's docstring literal, if its first statement is a bare string."""
    body = getattr(node, "body", None)
    if not body:
        return None
    first = body[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return first.value
    return None


def _is_field_call(func: ast.expr) -> bool:
    """True for ``Field(...)`` and ``pydantic.Field(...)``-style calls."""
    if isinstance(func, ast.Name):
        return func.id == "Field"
    return isinstance(func, ast.Attribute) and func.attr == "Field"


def audit_python_file(path: Path) -> list[str]:
    """Return unicode-math-glyph findings for one Python file.

    Walks every module/class/function docstring and every
    ``Field(description=...)`` string-constant keyword argument.
    ``kw.value`` must be a plain ``ast.Constant`` string; an f-string
    description (``ast.JoinedStr``) can't be statically inspected this way
    and is silently skipped rather than misreported.
    """
    label = str(path)
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=label)
    except SyntaxError as exc:
        return [f"{label}: could not parse for the Python LaTeX audit: {exc}"]

    issues: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = _docstring_constant(node)
            if doc is not None:
                issues += _string_glyph_findings(label, doc.value, doc.lineno, doc.col_offset)
        elif isinstance(node, ast.Call) and _is_field_call(node.func):
            for kw in node.keywords:
                if (
                    kw.arg == "description"
                    and isinstance(kw.value, ast.Constant)
                    and isinstance(kw.value.value, str)
                ):
                    issues += _string_glyph_findings(
                        label,
                        kw.value.value,
                        kw.value.lineno,
                        kw.value.col_offset,
                    )
    return issues


def audited_python_files() -> list[Path]:
    """Every Python file the mode-A pass covers."""
    return sorted(PYTHON_ROOT.rglob("*.py"))


def main() -> int:
    """Audit every covered file and print a summary; exit 1 on a hard issue."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python",
        action="store_true",
        help=(
            "Also run the report-only Python docstring/Field(description=...) "
            "unicode-math-glyph pass over python/**/*.py (mode A). Never "
            "affects the exit code unless PYTHON_LATEX_AUDIT_BLOCKING is True."
        ),
    )
    args = parser.parse_args()

    md_files = audited_files()
    all_issues: list[str] = []
    hard_issue = False
    for md_file in md_files:
        all_issues += audit_file(md_file)
    all_issues += audit_state()
    for issue in all_issues:
        if "[heuristic]" not in issue:
            hard_issue = True

    if not all_issues:
        print(
            f"audit_latex: clean — no issues across {len(md_files)} files and the manuscript state",
        )
    else:
        for issue in all_issues:
            print(issue)
        print(f"\naudit_latex: {len(all_issues)} finding(s)")

    run_python_pass = args.python or PYTHON_LATEX_AUDIT_BLOCKING
    if run_python_pass:
        python_files = audited_python_files()
        python_issues: list[str] = []
        for py_file in python_files:
            python_issues += audit_python_file(py_file)

        tag = "BLOCKING" if PYTHON_LATEX_AUDIT_BLOCKING else "python-report-only"
        if not python_issues:
            print(
                f"audit_latex --python: clean — no unicode math glyphs across "
                f"{len(python_files)} files under {PYTHON_ROOT}",
            )
        else:
            for issue in python_issues:
                print(f"[{tag}] {issue}")
            print(f"\naudit_latex --python: {len(python_issues)} finding(s)")
        if PYTHON_LATEX_AUDIT_BLOCKING and python_issues:
            hard_issue = True

    return 1 if hard_issue else 0


if __name__ == "__main__":
    sys.exit(main())
