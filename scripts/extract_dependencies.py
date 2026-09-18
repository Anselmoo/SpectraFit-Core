#!/usr/bin/env python3
"""Read the project's real dependency versions out of its manifests.

Written for the manuscript's Availability section, whose dependency list was
maintained by hand and had drifted from the manifests it claimed to describe. A
version number copied into prose is wrong by the time a paper is reviewed; this
script regenerates the list so the paper and the repository cannot disagree.

Three ecosystems are read, and they are not treated alike:

* **Python** from ``pyproject.toml`` ``[project].dependencies``, which is the
  runtime contract a user installs. Optional extras are read separately and
  labelled, because ``benchmark`` and ``jax`` are not needed to use the library.
* **Rust** from the workspace ``Cargo.toml`` ``[workspace.dependencies]``, which
  is where this workspace declares its shared versions.
* **JavaScript** from ``web/package.json``. These are reported as optional and
  development-only: the web front end is a report viewer, and nothing in the
  Python or Rust install path depends on it. The author's instruction was
  explicit that JS is "optional for debug mode", and the output says so rather
  than listing it beside the runtime dependencies.

Usage::

    python3 scripts/extract_dependencies.py                # markdown, to stdout
    python3 scripts/extract_dependencies.py --format json  # machine-readable
    python3 scripts/extract_dependencies.py --check        # exit 1 on drift

``--check`` compares the generated block against the one in
``manuscript/draft/sections/availability.md`` and fails if they differ, so the
drift this script exists to prevent cannot reappear silently.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AVAILABILITY = ROOT / "manuscript/draft/sections/availability.md"

BEGIN = "<!-- deps:begin -->"
END = "<!-- deps:end -->"


def _spec_version(spec: str) -> tuple[str, str]:
    """Split a PEP 508 requirement into its name and its version constraint."""
    name = re.split(r"[<>=!~\[;\s]", spec, maxsplit=1)[0].strip()
    constraint = spec[len(name) :].strip()
    return name, constraint


def python_deps() -> dict[str, object]:
    """Read runtime and optional Python dependencies from ``pyproject.toml``."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    project = data.get("project", {})
    build = data.get("build-system", {})
    runtime = [_spec_version(s) for s in project.get("dependencies", [])]
    extras = {
        name: [_spec_version(s) for s in specs]
        for name, specs in project.get("optional-dependencies", {}).items()
    }
    return {
        "requires_python": project.get("requires-python", ""),
        "runtime": runtime,
        "extras": extras,
        # For a package whose extension is compiled Rust behind PyO3, the build
        # backend is not a detail a reader can skip: it is what turns the crates
        # into the wheel. An earlier version read only [project] and omitted it.
        "build_requires": [_spec_version(x) for x in build.get("requires", [])],
        "build_backend": build.get("build-backend", ""),
    }


def rust_deps() -> dict[str, object]:
    """Read third-party crate versions from the workspace ``Cargo.toml``."""
    data = tomllib.loads((ROOT / "Cargo.toml").read_text())
    workspace = data.get("workspace", {})
    declared = workspace.get("dependencies", {})
    out: list[tuple[str, str]] = []
    for name, spec in sorted(declared.items()):
        # A workspace member is a path dependency on this repo, not a third
        # party, and listing eleven of our own crates as "dependencies" would
        # misrepresent the external surface the paper is describing.
        if isinstance(spec, dict):
            if "path" in spec:
                continue
            version = spec.get("version", "")
        else:
            version = str(spec)
        if version:
            out.append((name, version))
    return {
        "rust_version": workspace.get("package", {}).get("rust-version", ""),
        "runtime": out,
    }


def js_deps() -> dict[str, object]:
    """Read the web front end's packages, which are optional and debug-only."""
    path = ROOT / "web/package.json"
    if not path.is_file():
        return {"present": False, "runtime": [], "dev": []}
    data = json.loads(path.read_text())
    return {
        "present": True,
        "runtime": sorted(data.get("dependencies", {}).items()),
        "dev": sorted(data.get("devDependencies", {}).items()),
    }


def collect() -> dict[str, object]:
    """Read all three ecosystems into one structure."""
    return {"python": python_deps(), "rust": rust_deps(), "javascript": js_deps()}


# The venue spells zero to nine and uses figures from 10 up, so the table stops
# at nine rather than running to thirteen; `_count_word` falls back to digits.
_NUMBER_WORDS = {
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
}


def _member_crates() -> int:
    """Count the workspace's own crates on disk.

    This was written out as a word and drifted: the text said nine while 11
    existed. Counting the tree means the sentence cannot fall behind a crate
    being added.
    """
    return sum(1 for d in (ROOT / "crates").iterdir() if d.is_dir() and (d / "Cargo.toml").exists())


def _count_word(n: int) -> str:
    """Spell a small count, falling back to digits past the table."""
    return _NUMBER_WORDS.get(n, str(n))


def _join(pairs: list[tuple[str, str]], sep: str = ", ") -> str:
    return sep.join(
        f"{n}{v}" if v.startswith(("<", ">", "=", "!", "~")) else f"{n} {v}" for n, v in pairs
    )


def render_markdown(data: dict[str, object]) -> str:
    """Render the dependency data as the Availability section's marked block."""
    py = data["python"]
    rs = data["rust"]
    js = data["javascript"]

    lines = [BEGIN, ""]
    lines.append(
        f"Python {py['requires_python']} is required. Runtime dependencies are "
        f"{_join(py['runtime'])}.",
    )
    if py["extras"]:
        named = "; ".join(
            f"`{name}` ({_join(specs)})" for name, specs in sorted(py["extras"].items())
        )
        lines.append("")
        lines.append(f"Optional extras, not required to use the library: {named}.")
    lines.append("")
    if py["build_requires"]:
        lines.append(
            f"Building the extension from source needs {_join(py['build_requires'])} "
            f"as the build backend (`{py['build_backend']}`), which compiles the Rust "
            f"workspace into the PyO3 extension module the Python package imports. A "
            f"released wheel ships that module already built.",
        )
        lines.append("")
    lines.append(
        f"Rust {rs['rust_version']} or newer is required to build from source. The "
        f"workspace declares {len(rs['runtime'])} third-party crates, in full: "
        f"{_join(rs['runtime'])}. The {_count_word(_member_crates())} `spectrafit-*` "
        f"crates are members of this workspace rather than dependencies of it.",
    )
    if js["present"]:
        lines.append("")
        lines.append(
            f"The web front end is a report viewer and is not on the install path "
            f"for either the Python package or the Rust crates. Its "
            f"{len(js['runtime'])} runtime and {len(js['dev'])} development packages "
            f"are listed in `web/package.json` and pinned by "
            f"`web/package-lock.json`; they are needed only to rebuild the report "
            f"interface.",
        )
    lines.append("")
    lines.append(END)

    # Wrap to the manuscript sources' own column width so a regenerated block
    # produces no gratuitous diff against hand-written neighbours.
    wrapped: list[str] = []
    for line in lines:
        if not line or line.startswith("<!--"):
            wrapped.append(line)
        else:
            wrapped.extend(
                textwrap.wrap(line, width=79, break_long_words=False, break_on_hyphens=False),
            )
    return "\n".join(wrapped)


def main() -> int:
    """Print the dependency block, or check the manuscript against the manifests."""
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--format", choices=("markdown", "json"), default="markdown")
    ap.add_argument(
        "--check",
        action="store_true",
        help="compare against availability.md and exit 1 on drift",
    )
    args = ap.parse_args()

    data = collect()
    if args.format == "json":
        print(json.dumps(data, indent=2))
        return 0

    block = render_markdown(data)
    if not args.check:
        print(block)
        return 0

    text = AVAILABILITY.read_text()
    if BEGIN not in text or END not in text:
        print(f"error: {AVAILABILITY} carries no {BEGIN} … {END} block to check.", file=sys.stderr)
        return 1
    current = text[text.index(BEGIN) : text.index(END) + len(END)]
    if current.strip() == block.strip():
        print("dependencies: availability.md matches the manifests")
        return 0
    print(
        "dependencies: availability.md has DRIFTED from the manifests.\n"
        "This script only prints; it does not write. Replace the block between\n"
        f"{BEGIN} and {END} in\n"
        f"  {AVAILABILITY}\n"
        "with the output of:\n"
        "  uv run poe manuscript_deps",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
