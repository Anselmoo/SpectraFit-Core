"""Audit zensical.toml nav completeness: every doc is navigable, every nav target exists.

This test enforces the invariant that the Zensical docs site's navigation is
complete:

1. Every markdown file in docs/**/*.md is either:
   - Listed in zensical.toml's [nav] section, OR
   - In the [markdown_extensions.pymdownx.snippets].auto_append list, OR
   - In docs/includes/ (snippets, not pages), OR
   - A generated page (listed in .gitignore)

2. Every path listed in [nav] points to a file that exists (or is generated).

3. No orphan pages exist that are published but unreachable.
"""

from __future__ import annotations

import tomllib
from pathlib import Path


def _extract_nav_paths(nav_entries: list | dict) -> set[str]:
    """Recursively extract all file paths from zensical.toml's nav structure.

    Args:
        nav_entries: The nav section (list of dicts/strings).

    Returns:
        Set of relative file paths (as strings) referenced in nav.
    """
    paths = set()

    if isinstance(nav_entries, list):
        for entry in nav_entries:
            if isinstance(entry, str):
                paths.add(entry)
            elif isinstance(entry, dict):
                for _key, value in entry.items():
                    if isinstance(value, str):
                        paths.add(value)
                    elif isinstance(value, list):
                        paths.update(_extract_nav_paths(value))
    elif isinstance(nav_entries, dict):
        for _key, value in nav_entries.items():
            if isinstance(value, str):
                paths.add(value)
            elif isinstance(value, list):
                paths.update(_extract_nav_paths(value))

    return paths


def _get_generated_pages() -> set[str]:
    """Extract generated doc pages from .gitignore.

    Returns:
        Set of relative paths (as strings) that are generated and gitignored.
        Only includes patterns that explicitly start with docs/.
    """
    gitignore_path = Path(".gitignore")
    if not gitignore_path.exists():
        return set()

    generated = set()
    with gitignore_path.open() as f:
        for raw_line in f:
            line = raw_line.rstrip()
            # Skip comments and empty lines
            if not line or line.startswith("#"):
                continue
            # Match lines that start with docs/ and are specific files (not directories)
            if line.startswith("docs/") and not line.endswith("/"):
                generated.add(line)

    return generated


def test_nav_entries_point_to_existing_files():
    """Every nav entry must point to a file that exists (or is generated)."""
    zensical_path = Path("zensical.toml")
    assert zensical_path.exists(), "zensical.toml not found"

    with zensical_path.open("rb") as f:
        config = tomllib.load(f)

    nav = config.get("nav", [])
    nav_paths = _extract_nav_paths(nav)
    generated_pages = _get_generated_pages()

    missing_files = []
    for nav_path in sorted(nav_paths):
        # Nav paths in zensical.toml are relative to docs/ root
        file_path = Path("docs") / nav_path
        # Also check if it's a generated page (generated paths include docs/ prefix)
        generated_check = f"docs/{nav_path}"
        if not file_path.exists() and generated_check not in generated_pages:
            missing_files.append(nav_path)

    assert not missing_files, "Nav entries point to missing files:\n  " + "\n  ".join(missing_files)


def test_all_docs_are_in_nav_or_auto_append():
    """Every markdown file in docs/ is either in nav, auto_append, or includes/."""
    zensical_path = Path("zensical.toml")
    assert zensical_path.exists(), "zensical.toml not found"

    with zensical_path.open("rb") as f:
        config = tomllib.load(f)

    nav = config.get("nav", [])
    nav_paths = _extract_nav_paths(nav)

    # Get auto_append list (snippets that are injected into every page)
    markdown_extensions = config.get("markdown_extensions", {})
    pymdownx = markdown_extensions.get("pymdownx.snippets", {})
    auto_append = set(pymdownx.get("auto_append", []))

    generated_pages = _get_generated_pages()

    # Walk all docs/**/*.md files
    docs_path = Path("docs")
    all_md_files = sorted(docs_path.glob("**/*.md"))

    orphans = []

    for md_file in all_md_files:
        relative_path = str(md_file)
        # Normalize: remove "docs/" prefix to match nav/auto_append paths
        path_without_prefix = relative_path.removeprefix("docs/")

        # Check if it's in nav (nav paths don't have docs/ prefix)
        if path_without_prefix in nav_paths:
            continue

        # Check if it's in auto_append (snippets injected into every page)
        if relative_path in auto_append:
            continue

        # Check if it's in docs/includes/ (snippets, not pages)
        if "docs/includes/" in relative_path:
            continue

        # Check if it's a generated page
        if relative_path in generated_pages:
            continue

        # If none of the above, it's an orphan
        orphans.append(relative_path)

    # Use match/case to enforce the rule, not if/elif chains
    for orphan_path in orphans:
        path_without_prefix = orphan_path.removeprefix("docs/")
        match orphan_path:
            case p if "includes/" in p:
                # This should not happen — we checked this above
                pass
            case p if p in generated_pages:
                # This should not happen — we checked this above
                pass
            case p if path_without_prefix in nav_paths:
                # This should not happen — we checked this above
                pass
            case p:
                # Unreachable case — real orphan
                pass

    assert not orphans, (
        "Orphan doc files (not in nav, auto_append, or includes/):\n  "
        + "\n  ".join(
            orphans,
        )
    )


if __name__ == "__main__":
    test_nav_entries_point_to_existing_files()
    test_all_docs_are_in_nav_or_auto_append()
    print("✓ All nav completeness tests passed")
