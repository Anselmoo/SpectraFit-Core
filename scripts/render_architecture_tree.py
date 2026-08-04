"""Regenerate the directory-tree block in contributor-guide/architecture.md.

Wraps `rrt tree` (the MCP tool only reads an existing `.rrt/tree.lock.toml`;
it can't generate or filter one — see the CLI invocation this replaces) and
filters out top-level entries that don't belong in a reader-facing
architecture overview:

- `analysis/` — excluded from the GitHub mirror publish entirely
  (`pyproject.toml`'s `[tool.rrt.publish_targets.github].exclude`), so
  listing it here is actively wrong on that mirror, not just noise.
- `test-results/`, `vibe-sessions/` — empty scratch directories (a
  Playwright run marker and a `.gitkeep` respectively), no architectural
  content.

A naive full-repo dump is not the more "honest" choice here despite the
plain reading of that principle — the previous version of this fix showed
everything unfiltered, which was accurate for GitLab but actively
misleading on the GitHub mirror, where `analysis/` does not exist at all.

Uses `--format ascii` (a real `|--`/`` `-- `` box-drawing tree), not
`--format markdown`: the markdown format's 2-space nested-bullet indentation
doesn't meet most Markdown parsers' 4-space (or content-aligned) threshold
for a nested list, so every entry — regardless of actual depth — rendered
as one long flat top-level bullet list with no visible hierarchy. Wrapping
the ascii tree in a fenced code block avoids that parser dependency
entirely and reads as an actual tree, not a wall of ~100 flat bullets.

Usage: `uv run python scripts/render_architecture_tree.py` (writes the
filtered block between the `<!-- rrt:auto:start:dirtree -->` /
`<!-- rrt:auto:end:dirtree -->` markers in
`docs/contributor-guide/architecture.md`). Run `rrt tree --root . --max-depth
2 --snapshot` first (or let this script do it) to refresh `.rrt/tree.lock.toml`
before checking for drift with `rrt tree --root . --max-depth 2 --check`.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARCHITECTURE_MD = REPO_ROOT / "docs" / "contributor-guide" / "architecture.md"
ANCHOR = "dirtree"
START_MARKER = f"<!-- rrt:auto:start:{ANCHOR} -->"
END_MARKER = f"<!-- rrt:auto:end:{ANCHOR} -->"

# Top-level entries to drop from the rendered tree — see the module
# docstring for why each one is excluded.
EXCLUDED_TOP_LEVEL = ("analysis/", "test-results/", "vibe-sessions/")


def _run_rrt_tree() -> str:
    result = subprocess.run(
        ["rrt", "tree", "--root", ".", "--format", "ascii", "--max-depth", "2"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def filter_tree(ascii_tree: str) -> str:
    """Strip rrt's CLI banner/footer and drop each excluded top-level entry + children.

    `rrt tree` without `--inject` prints a Rich-formatted banner ("Project
    tree" header, "-> Root/Format/..." lines, a "-- Tree --" divider) and a
    "Done. N entries shown." footer around the actual tree — none of that
    belongs in the doc. Real tree lines always start with either `|` (a
    branch marker or a mid-list continuation) or `` ` `` (the last branch at
    that depth); banner/footer lines never do (they start with `✔`, `→`, the
    Unicode box-divider `─`, or are blank).
    """
    kept: list[str] = []
    skipping = False
    for line in ascii_tree.splitlines():
        if not line or line[0] not in "|`":
            continue  # banner, footer, or divider line
        is_top_level = line.startswith(("|--", "`--"))
        if is_top_level:
            skipping = any(
                line.startswith((f"|-- {name}", f"`-- {name}"))
                for name in EXCLUDED_TOP_LEVEL
            )
        if not skipping:
            kept.append(line)
    return "```text\n" + "\n".join(kept) + "\n```"


def splice(architecture_text: str, filtered_tree: str) -> str:
    """Replace the anchored block in `architecture_text` with `filtered_tree`."""
    start_idx = architecture_text.index(START_MARKER) + len(START_MARKER)
    end_idx = architecture_text.index(END_MARKER)
    return (
        architecture_text[:start_idx]
        + "\n"
        + filtered_tree
        + "\n"
        + architecture_text[end_idx:]
    )


def main() -> int:
    """Regenerate and write the filtered directory tree into architecture.md."""
    raw_tree = _run_rrt_tree()
    filtered = filter_tree(raw_tree)
    architecture_text = ARCHITECTURE_MD.read_text(encoding="utf-8")
    updated = splice(architecture_text, filtered)
    ARCHITECTURE_MD.write_text(updated, encoding="utf-8")
    print(
        f"wrote filtered tree ({len(filtered.splitlines())} lines) into {ARCHITECTURE_MD}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
