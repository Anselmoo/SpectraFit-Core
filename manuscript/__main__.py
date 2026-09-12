#!/usr/bin/env python3
"""The one entry point for every manuscript tool.

Why this exists
---------------
These seven tools used to be reachable only as ``poe`` tasks, which meant
``pyproject.toml`` carried six ``cmd = "python manuscript/<script>.py"`` lines.
That put the manuscript's build wiring inside the *package's* configuration
file, where it does not belong: `pyproject.toml` describes how to build and
test spectrafit-core, and the manuscript is a separate deliverable that merely
lives in the same repository. A reader of `pyproject.toml` should not have to
learn the manuscript's toolchain to understand the package's.

So the tasks are gone and this dispatcher replaces them. `pyproject.toml` no
longer names a single path under `manuscript/` for task execution -- the only
`manuscript/` strings left in it are the rrt publish-exclusion patterns, which
are a **safety** mechanism (they keep the private draft, the readiness audit and
the review correspondence out of the public GitHub mirror) and must stay.

Usage
-----
    uv run python manuscript --help
    uv run python manuscript figures --check
    uv run python manuscript checksums --check
    uv run python manuscript fecl4
    uv run python manuscript fair --verify <dir>
    uv run python manuscript render --check

Every argument after the command is forwarded verbatim to that tool, so each
tool's own ``--help`` remains the authority on its flags:

    uv run python manuscript figures --help

Dispatch is by import-and-call rather than subprocess: each tool exposes a
``main()`` returning a process exit code (or ``None``), and this file sets
``sys.argv`` around the call so their argparse parsers see exactly what they
would have seen when invoked directly. Running them as subprocesses would work
too, but would hide their exit codes behind a shell and double the interpreter
startup on a gate that runs four of them in a row.
"""

from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

# Each tool is a sibling module in this directory, not an installed package.
sys.path.insert(0, str(Path(__file__).resolve().parent))

# command -> (module, one-line help). The command names are deliberately shorter
# than the module names: `figures`, not `render_figures`.
COMMANDS: dict[str, tuple[str, str]] = {
    "figures": ("render_figures", "Render every manuscript figure; --check reports drift only"),
    "fecl4": (
        "check_fecl4_scenarios",
        "Fail if fecl4_constraint_scenarios.json drifted from a fresh run",
    ),
    "checksums": (
        "manuscript_checksums",
        "Integrity manifest over every measured artifact; --check verifies",
    ),
    "fair": ("build_fair_package", "Assemble the FAIR data package; --verify <dir> checks one"),
    "render": ("render_manuscript", "Render the manuscript; --check reports staleness"),
    "annotate": ("annotate_docx", "Write reviewer findings into a .docx as margin comments"),
    "comments": ("read_docx_comments", "Read author comments back out of a reviewed .docx"),
}


def _run(command: str, argv: list[str]) -> int:
    module_name, _ = COMMANDS[command]
    module = importlib.import_module(module_name)
    # argv[0] is conventionally the program name; give the tool its own so its
    # --help and error messages name the module a reader can actually open.
    saved = sys.argv
    sys.argv = [f"{module_name}.py", *argv]
    try:
        result = module.main()
    finally:
        sys.argv = saved
    # render_manuscript and read_docx_comments return None on success.
    return 0 if result is None else int(result)


def main() -> int:
    """Dispatch to one manuscript tool, forwarding the remaining arguments."""
    width = max(len(c) for c in COMMANDS)
    listing = "\n".join(f"  {c:<{width}}  {h}" for c, (_, h) in COMMANDS.items())
    parser = argparse.ArgumentParser(
        prog="python manuscript",
        description=__doc__.split("Usage")[0].strip(),
        epilog=f"commands:\n{listing}\n\nRun `python manuscript <command> --help` for a tool's own flags.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("command", choices=sorted(COMMANDS), metavar="command")
    parser.add_argument("args", nargs=argparse.REMAINDER, metavar="...")
    ns = parser.parse_args()
    return _run(ns.command, ns.args)


if __name__ == "__main__":
    raise SystemExit(main())
