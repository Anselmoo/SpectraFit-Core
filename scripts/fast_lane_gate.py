#!/usr/bin/env python3
"""Fast-lane publish diff-gate for publish:github:fast.

Given the currently-published GitHub `main` SHA (base) and a head ref
(default HEAD), asserts the change is safe to publish without waiting for
the full GitLab CI pipeline: every changed path (after filtering the shared
publish-exclusion patterns) must live under `.github/`, and every changed
`.yml`/`.yaml` path among them must parse as valid YAML.

GitLab CI never executes `.github/**` at all, so waiting for the full
pipeline (lint/test/coverage/build/pages) buys zero extra safety for this
class of change — only latency. See
docs/superpowers/specs/2026-07-11-github-publish-fast-lane-design.md.

If the gate fails for any reason, it exits 1 with a message identifying the
offending path(s)/error and pointing at the full-pipeline `publish:github`
job as the fallback.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from publish_exclusions import filter_excluded  # noqa: E402

_GITHUB_PREFIX = ".github/"
_FALLBACK_MESSAGE = (
    "Use the full-pipeline `publish:github` job instead — it waits for "
    "lint/test/coverage/build/pages before publishing."
)


class GitDiffError(Exception):
    """Raised when git diff fails (e.g., invalid/unreachable base_ref)."""


def _git_diff_names(base_ref: str, head_ref: str) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", base_ref, head_ref],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        error_msg = exc.stderr or exc.stdout or str(exc)
        raise GitDiffError(
            f"Could not diff {base_ref}..{head_ref}: {error_msg}"
        ) from exc
    return [line for line in result.stdout.splitlines() if line]


def classify_paths(paths: list[str]) -> tuple[list[str], list[str]]:
    """Filter shared exclusions, then split into (kept, offending).

    `kept` is every changed path after removing known-excluded paths.
    `offending` is the subset of `kept` NOT starting with `.github/`.
    """
    kept = filter_excluded(paths)
    offending = [path for path in kept if not path.startswith(_GITHUB_PREFIX)]
    return kept, offending


def check_yaml_paths(repo_root: Path, paths: list[str]) -> list[tuple[str, str]]:
    """Return (path, error) for every .yml/.yaml path that fails to parse."""
    import yaml

    failures: list[tuple[str, str]] = []
    for path in paths:
        if not (path.endswith(".yml") or path.endswith(".yaml")):
            continue
        full_path = repo_root / path
        if not full_path.exists():
            continue  # deleted in the diff — nothing to parse
        try:
            yaml.safe_load(full_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            failures.append((path, str(exc)))
    return failures


def main() -> int:
    """Parse CLI args and run the fast-lane diff-gate."""
    parser = argparse.ArgumentParser(
        description="Fast-lane diff-gate for publish:github:fast."
    )
    parser.add_argument("base_ref", help="Base ref (the published GitHub main SHA).")
    parser.add_argument(
        "head_ref", nargs="?", default="HEAD", help="Head ref (default: HEAD)."
    )
    args = parser.parse_args()

    repo_root = Path.cwd()
    try:
        changed_paths = _git_diff_names(args.base_ref, args.head_ref)
    except GitDiffError as exc:
        print(f"fast_lane_gate: FAILED — {exc}")
        print(_FALLBACK_MESSAGE)
        return 1

    kept, offending = classify_paths(changed_paths)
    if offending:
        print("fast_lane_gate: FAILED — non-.github/ path(s) changed:")
        for path in offending:
            print(f"  {path}")
        print(_FALLBACK_MESSAGE)
        return 1

    # Defense-in-depth: explicitly filter kept to exclude offending paths
    # (offending is empty here, but this guards against future refactors
    # that might change the control flow order).
    kept_for_yaml = [p for p in kept if p not in offending]
    yaml_failures = check_yaml_paths(repo_root, kept_for_yaml)
    if yaml_failures:
        print("fast_lane_gate: FAILED — invalid YAML in changed path(s):")
        for path, error in yaml_failures:
            print(f"  {path}: {error}")
        print(_FALLBACK_MESSAGE)
        return 1

    print(
        f"fast_lane_gate: OK — {len(kept)} changed path(s), "
        "all under .github/ and valid YAML."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
