"""No code in this repo may set ``XLA_FLAGS`` to a string XLA would silently ignore.

WHY THIS EXISTS. XLA parses ``XLA_FLAGS`` with a flag parser that treats anything
without a leading ``--`` as a positional argument and drops it **without a word**. An
unknown ``--``-prefixed flag, by contrast, aborts the process with
``Unknown flag in XLA_FLAGS``. So the two ways of getting a flag wrong fail in exactly
opposite ways, and only one of them is visible.

``scripts/bench_ladder.py`` shipped
``XLA_FLAGS="--xla_cpu_multi_thread_eigen=false intra_op_parallelism_threads=1"`` as a
fix for the reps ladder dying on every rung. The second token has no ``--``, so it never
took effect; the run kept dying, and the inert setting was recorded into every rung's
``provenance.json`` as though it had been applied. A guard on the one literal that
caused it would be worthless — this guards the class.

The rule: every whitespace-separated token of any ``XLA_FLAGS`` value this repo
*assigns* must begin with ``--``. Prose that merely mentions the variable is not an
assignment and is not matched.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SEARCH_ROOTS = ("python", "scripts", "tests", ".gitlab-ci.yml", ".github")
SUFFIXES = {".py", ".sh", ".toml", ".yml", ".yaml"}

# `XLA_FLAGS=…` / `"XLA_FLAGS": …` followed by a quoted literal — an assignment, not a
# mention. Group 1 is the value.
_ASSIGNMENT = re.compile(
    r"""XLA_FLAGS["']?\s*[:=]\s*(?:f?["'])([^"']*)["']""",
)


def _candidate_files() -> list[Path]:
    """Every tracked source file that could plausibly set the variable.

    This file is excluded: it quotes the malformed original on purpose, and a guard
    that fails on its own worked example is a guard nobody keeps.
    """
    out: list[Path] = []
    for root in SEARCH_ROOTS:
        target = REPO / root
        if target.is_file():
            out.append(target)
        elif target.is_dir():
            out += [
                p
                for p in target.rglob("*")
                if p.suffix in SUFFIXES and "__pycache__" not in p.parts
            ]
    return [p for p in out if p != Path(__file__).resolve()]


def _code_only(text: str) -> str:
    """Drop whole-line comments, so documenting the old defect does not trip the guard.

    Both ``bench_ladder.py`` and this module quote the malformed string in prose to
    explain what went wrong. Only a live assignment is a defect.
    """
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith(("#", "*")))


@pytest.mark.parametrize("path", _candidate_files(), ids=lambda p: str(p.relative_to(REPO)))
def test_every_assigned_xla_flag_is_dash_prefixed(path: Path) -> None:
    """Reject any assigned ``XLA_FLAGS`` token XLA would drop on the floor."""
    text = _code_only(path.read_text(encoding="utf-8", errors="replace"))
    for value in _ASSIGNMENT.findall(text):
        bad = [tok for tok in value.split() if tok and not tok.startswith("--")]
        assert not bad, (
            f"{path.relative_to(REPO)} sets XLA_FLAGS={value!r}; "
            f"token(s) {bad} lack a leading '--' and XLA will discard them silently"
        )


def test_the_guard_would_catch_the_original_defect() -> None:
    """The regex must actually match the shape of the bug it was written for."""
    sample = 'env = {"XLA_FLAGS": "--xla_cpu_multi_thread_eigen=false intra_op=1"}'
    (value,) = _ASSIGNMENT.findall(sample)
    assert [tok for tok in value.split() if not tok.startswith("--")] == ["intra_op=1"]


def test_bench_ladder_no_longer_injects_flags() -> None:
    """The ladder runs jax at stock defaults; it records ``XLA_FLAGS``, never sets it.

    Measured: the removed flags changed nothing (1.76 GB with, 1.75 GB without, over
    the full 127-case sweep). The real limit was ``vm.max_map_count``, fixed in the jax
    backend. Re-introducing a flag here would put a thumb on the comparator's scale for
    no benefit.
    """
    source = _code_only((REPO / "scripts" / "bench_ladder.py").read_text(encoding="utf-8"))
    assert not _ASSIGNMENT.findall(source), "bench_ladder.py assigns XLA_FLAGS again"
    assert 'os.environ.get("XLA_FLAGS"' in source, "the operator's XLA_FLAGS is not recorded"
