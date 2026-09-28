"""Guard: a published test must not read a path that is never published.

A test that ships to the public GitHub mirror but opens a file outside the
publish scope (``scripts/publish_exclusions.py``) can never pass there, however
green it is on GitLab, because the file does not exist on the mirror. This
module catches that class of test at authoring time.

**Method.** Every git-tracked ``tests/**/*.py`` file that itself ships (i.e. is
inside the publish scope defined by ``scripts/publish_exclusions.py``) is
parsed with :mod:`ast` and scanned for path-like string literals — both bare
string constants and ``Path(...) / "a" / "b"``-style chains of ``/`` operators,
whose trailing run of string-constant operands is joined into ``"a/b"``. A
literal is flagged when it names a private location of this repository: its
first segment is one of ``PRIVATE_ROOTS`` (``"analysis"`` alone counts), or it
lies under a published directory but matches an ``EXCLUDE_PATTERNS`` entry
(``docs/superpowers/...``). Arbitrary words are not repo paths and are ignored,
even though the include list technically treats them as unpublished.

**False positives are expected and are not this module's job to silence.**
Some shipped tests (``tests/meta/test_publish_exclusions.py``,
``test_publish_remove_excluded.py``, ``test_fast_lane_gate.py``,
``test_publish_sync.py``) legitimately
use excluded-looking path strings as fixture data inside a scratch
``tmp_path`` repo they construct themselves, to test the exclusion machinery
*itself* — they never read those paths from the real, shipped checkout. A test
that deliberately skips when an excluded directory is absent (a
``skipif``-guarded check) is the other legitimate shape this can flag. Either
case is silenced per-line with a trailing ``# publish-excluded-ok: <reason>``
comment — but adding that comment to a file this module does not own is out
of scope here; unmarked hits found on a real run are reported to the
orchestrator instead of being suppressed by fiat (see the calling task's
instructions and, if this test currently fails, the accompanying report's
``open_issues``).
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from publish_exclusions import (  # ty: ignore[unresolved-import]
    PRIVATE_ROOTS,
    PUBLISH_INCLUDE,
    is_excluded,
)

_OPT_OUT_MARKER = "publish-excluded-ok:"
_WHITESPACE_RE = re.compile(r"\s")
_PATH_LIKE_RE = re.compile(r"[\w][\w.\-/]*")


_PUBLISHED_ROOTS = frozenset(pattern[:-2] for pattern in PUBLISH_INCLUDE if pattern.endswith("/*"))


def _literal_is_excluded(literal: str) -> bool:
    """True if *literal*, read as a repo-relative path, names a private location."""
    normalised = literal.strip("/")
    first = normalised.split("/", 1)[0]
    if first in PRIVATE_ROOTS:
        return True
    return "/" in normalised and first in _PUBLISHED_ROOTS and is_excluded(normalised)


def _looks_like_path(value: str) -> bool:
    """Cheap path-ish heuristic: no whitespace, and nothing but word/path chars.

    Deliberately permissive (a bare word like ``"analysis"`` passes) — the
    real filter is ``_literal_is_excluded``, which only matches literals that
    name a private location of this repository. Over-accepting here just means a
    few more strings get checked against the pattern list; it costs nothing
    and avoids re-litigating what "looks like a path" means for every odd
    literal a test file might contain.
    """
    if not value or _WHITESPACE_RE.search(value):
        return False
    return _PATH_LIKE_RE.fullmatch(value) is not None


def _flatten_div_chain(node: ast.expr) -> list[ast.expr]:
    """Flatten a left-associative chain of ``BinOp(op=Div)`` into its operands.

    ``a / "b" / "c"`` parses as ``BinOp(BinOp(a, Div, "b"), Div, "c")``; this
    returns ``[a, "b", "c"]`` in source order for any node, constant or not.
    """
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return [*_flatten_div_chain(node.left), *_flatten_div_chain(node.right)]
    return [node]


def _is_chain_top(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    """True if *node* is the outermost ``BinOp(Div)`` of its chain.

    Every inner ``BinOp`` in a chain is also visited by :func:`ast.walk`; only
    processing the outermost one avoids flagging the same trailing run twice
    (once for the full chain, once for each of its own sub-chains).
    """
    parent = parents.get(node)
    return not (isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div))


def scan_source(source: str, *, filename: str = "<source>") -> list[tuple[int, str]]:
    """Return ``(lineno, literal)`` for every excluded-looking path literal.

    Two literal shapes are recognised: a bare string constant, and a
    ``Path(...) / "a" / "b"``-style ``/``-chain, whose trailing run of
    string-constant operands is joined with ``"/"`` (``REPO_ROOT / "a" / "b"``
    becomes ``"a/b"`` — the leading non-constant operand is dropped). A line
    carrying ``# publish-excluded-ok: <reason>`` anywhere across the flagged
    node's span is never reported. Invalid source parses to no findings rather
    than raising, so a caller scanning many files can just skip unparseable
    ones instead of special-casing them.
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return []

    lines = source.splitlines()

    def _opts_out(lineno: int, end_lineno: int | None) -> bool:
        end = end_lineno or lineno
        return any(
            _OPT_OUT_MARKER in lines[n - 1] for n in range(lineno, end + 1) if 1 <= n <= len(lines)
        )

    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child] = node

    offenders: list[tuple[int, str]] = []
    absorbed: set[int] = set()  # id() of Constant nodes already reported via a chain

    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Div)
            and _is_chain_top(node, parents)
        ):
            continue
        leaves = _flatten_div_chain(node)
        trailing_values: list[str] = []
        trailing_nodes: list[ast.Constant] = []
        for leaf in reversed(leaves):
            if isinstance(leaf, ast.Constant) and isinstance(leaf.value, str):
                trailing_values.insert(0, leaf.value)
                trailing_nodes.insert(0, leaf)
            else:
                break
        if not trailing_values:
            continue
        for leaf_node in trailing_nodes:
            absorbed.add(id(leaf_node))
        joined = "/".join(trailing_values)
        if not (_looks_like_path(joined) and _literal_is_excluded(joined)):
            continue
        start = trailing_nodes[0].lineno
        end = getattr(node, "end_lineno", start)
        if not _opts_out(start, end):
            offenders.append((start, joined))

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
            continue
        if id(node) in absorbed:
            continue
        value = node.value
        if not (_looks_like_path(value) and _literal_is_excluded(value)):
            continue
        end = getattr(node, "end_lineno", node.lineno)
        if _opts_out(node.lineno, end):
            continue
        offenders.append((node.lineno, value))

    offenders.sort(key=lambda pair: pair[0])
    return offenders


# Tests whose SUBJECT is the exclusion machinery itself. They build scratch
# repositories out of excluded-looking paths on purpose, so every literal in
# them would be a false positive. Exempted by file rather than by ~20 per-line
# opt-outs; anything added to this set should be of the same kind. This module
# itself belongs here too: its own self-tests below (`test_scan_source_*`)
# embed excluded-looking literals as synthetic fixture source strings (and in
# the assertions checking `scan_source`'s output against them) to exercise the
# scanner directly — never a real read of the shipped tree — so scanning this
# file's own source would otherwise flag itself.
_EXCLUSION_MACHINERY_TESTS = frozenset(
    {
        "tests/meta/test_fast_lane_gate.py",
        "tests/meta/test_guard_public_push.py",
        "tests/meta/test_publish_exclusions.py",
        "tests/meta/test_publish_remove_excluded.py",
        "tests/meta/test_publish_sync.py",
        # This file's own scanner self-tests feed it excluded literals on purpose.
        "tests/meta/test_shipped_tests_read_no_excluded_paths.py",
    },
)


def _shipped_test_files() -> list[Path]:
    """Every git-tracked ``tests/**/*.py`` file that itself ships publicly."""
    tracked = subprocess.run(
        ["git", "ls-files", "--", "tests"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    return [
        REPO_ROOT / relpath
        for relpath in tracked
        if relpath.endswith(".py")
        and not is_excluded(relpath)
        and relpath not in _EXCLUSION_MACHINERY_TESTS
    ]


def test_shipped_tests_do_not_read_excluded_paths() -> None:
    offenders: list[str] = []
    for path in _shipped_test_files():
        relpath = path.relative_to(REPO_ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        offenders.extend(
            f"{relpath}:{lineno}: {literal}"
            for lineno, literal in scan_source(source, filename=relpath)
        )
    assert not offenders, (
        "shipped test file(s) contain a path literal naming a GitHub-mirror "
        "private location (scripts/publish_exclusions.PRIVATE_ROOTS / EXCLUDE_PATTERNS) — a "
        "test reading one of these paths can never pass on the public mirror. "
        "If a hit "
        "is a legitimate fixture/skipif literal rather than a real read of "
        "the shipped tree, silence it in place with a trailing "
        "'# publish-excluded-ok: <reason>' comment on the flagged line:\n" + "\n".join(offenders)
    )


# --- Self-tests for the scanner, factored out above so it can be exercised
# --- directly against synthetic source strings, independent of the current
# --- state of the real test suite. ---------------------------------------


def test_scan_source_flags_a_bare_excluded_literal() -> None:
    source = 'PATH = "analysis/crates/PREFLIGHT.md"\n'
    assert scan_source(source) == [(1, "analysis/crates/PREFLIGHT.md")]


def test_scan_source_flags_a_bare_excluded_directory_prefix() -> None:
    """A literal equal to a private root's own name is flagged too."""
    source = 'PATH = "analysis"\n'
    assert scan_source(source) == [(1, "analysis")]


def test_scan_source_flags_an_excluded_div_chain() -> None:
    source = 'PATH = REPO_ROOT / "docs" / "superpowers" / "plans" / "x.md"\n'
    assert scan_source(source) == [(1, "docs/superpowers/plans/x.md")]


def test_scan_source_does_not_flag_a_clean_literal() -> None:
    source = 'PATH = "python/oracles/nist_strd"\n'
    assert scan_source(source) == []


def test_scan_source_does_not_flag_a_clean_div_chain() -> None:
    source = 'PATH = REPO_ROOT / "python" / "oracles" / "nist_strd"\n'
    assert scan_source(source) == []


def test_scan_source_ignores_non_path_looking_strings() -> None:
    source = 'MSG = "hello world, this has spaces and punctuation!"\n'
    assert scan_source(source) == []


def test_scan_source_respects_the_opt_out_comment() -> None:
    source = 'PATH = "analysis/crates/PREFLIGHT.md"  # publish-excluded-ok: scratch fixture\n'
    assert scan_source(source) == []


def test_scan_source_opt_out_covers_the_whole_div_chain_span() -> None:
    source = (
        "PATH = (\n"
        '    REPO_ROOT / "docs" / "superpowers"\n'
        '    / "plans" / "x.md"  # publish-excluded-ok: scratch fixture\n'
        ")\n"
    )
    assert scan_source(source) == []


def test_scan_source_returns_nothing_for_unparseable_source() -> None:
    assert scan_source("def f(:\n") == []
