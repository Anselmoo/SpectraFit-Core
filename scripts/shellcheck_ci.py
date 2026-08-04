#!/usr/bin/env python3
"""ShellCheck the shell embedded in GitLab CI YAML.

`actionlint` already shellchecks `.github/workflows/**` `run:` blocks — it invokes
shellcheck automatically whenever shellcheck is on PATH (which is *why* an
"actionlint clean" result meant much less than it appeared to before shellcheck
was installed). Nothing did the equivalent for `.gitlab/**`, whose jobs carry the
larger share of this repo's inline shell.

Two details make this more than a `shellcheck **/*.yml` one-liner:

1. **`!reference` tags.** GitLab's `!reference [.rules_default, rules]` is not
   standard YAML and `yaml.SafeLoader` rejects the whole file. A tolerant loader
   that maps the tag to `None` is the shape `ci-config-guard-test-subject-arrangement`
   prescribes, and it is what lets this script parse structure instead of
   grepping text.

2. **A job's `script:` entries must be concatenated before checking, not checked
   one at a time.** GitLab runs all of a job's entries in ONE shell, so variables
   set in one entry are used in a later one. Checking entries individually makes
   shellcheck report false SC2034 "appears unused" — e.g. `publish:github:fast`
   sets `GITHUB_SHA=$(git rev-parse github/main)` in `script[5]` and uses it in
   `script[8]`. That split is not incidental: `.gitlab/70-publish.yml` uses one
   `- |` block *per command* deliberately, so GitLab aborts the job on the first
   failing list item (see DECISIONS.md, 2026-08-02). Concatenating restores the
   shell's real view without giving up that abort semantics.

Exit 0 when the finding count is at or below the baseline, 1 otherwise. The
baseline exists because the three current findings are pre-existing; gating at
zero would mean fixing unrelated code under time pressure. Lower it as they are
cleared — never raise it without saying why.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

#: Findings tolerated today, all three pre-existing and none introduced by the
#: 2026-08-02 consistency pass:
#:   SC1090  .gitlab/30-test.yml  test:python:rust-cov  `source <(cargo llvm-cov show-env --sh)`
#:   SC2034  .gitlab/30-test.yml  test:web              `for i in $(seq 1 60)` — counter genuinely unused
#:   SC2155  .gitlab/70-publish.yml publish:github:fast `export VAR=$(...)` masks the return value
#: Checking entries individually reported a FOURTH — `GITHUB_SHA appears unused`
#: — which concatenation proved to be a false positive (it is used three entries
#: later). Lower this as the real three are fixed; raising it needs a reason.
BASELINE = 3

#: Severities that count as defects. shellcheck's ladder is
#: error > warning > info > style; only `style` is pure preference.
#:
#: Parse JSON, NOT `--format=gcc`. gcc format collapses BOTH `info` and `style`
#: into the same `note:` prefix, so filtering on `note:` silently discards every
#: info-level finding — including SC2086 (unquoted variable), which is exactly
#: the class of bug this gate exists to catch in CI shell. Verified: an injected
#: `[ -z $UNQUOTED ]` produced `note: ... [SC2086]` under gcc and was dropped,
#: leaving the gate green on a real defect.
_REPORTED_LEVELS = frozenset({"error", "warning", "info"})

SCRIPT_KEYS = ("script", "before_script", "after_script")


class _TolerantLoader(yaml.SafeLoader):
    """SafeLoader that tolerates GitLab's `!reference` tag."""


_TolerantLoader.add_constructor("!reference", lambda _loader, _node: None)


def _jobs(path: Path) -> dict[str, dict]:
    doc = yaml.load(path.read_text(), Loader=_TolerantLoader) or {}
    return {k: v for k, v in doc.items() if isinstance(v, dict)}


def _findings(script: str) -> list[str]:
    proc = subprocess.run(
        ["shellcheck", "--shell=bash", "--format=json", "-"],
        input=script,
        capture_output=True,
        text=True,
        check=False,
    )
    if not proc.stdout.strip():
        return []
    try:
        items = json.loads(proc.stdout)
    except json.JSONDecodeError:
        # shellcheck failed to run at all (missing binary, bad flag). Surface it
        # rather than reporting a reassuring zero.
        raise SystemExit(
            f"shellcheck_ci: could not parse shellcheck output: "
            f"{(proc.stderr or proc.stdout)[:200]}"
        ) from None
    return [
        f"{i['level']}: {i['message']} [SC{i['code']}]"
        for i in items
        if i.get("level") in _REPORTED_LEVELS
    ]


def main() -> int:
    """ShellCheck every GitLab CI job's shell; return 1 if findings exceed BASELINE."""
    root = Path(__file__).resolve().parents[1]
    targets = sorted((root / ".gitlab").glob("*.yml"))
    ci_root = root / ".gitlab-ci.yml"
    if ci_root.exists():
        targets.append(ci_root)

    if not targets:
        print("shellcheck_ci: no .gitlab/*.yml found — nothing to check")
        return 0

    total: list[str] = []
    for path in targets:
        for job, body in _jobs(path).items():
            for key in SCRIPT_KEYS:
                entries = body.get(key)
                if not isinstance(entries, list):
                    continue
                # Concatenate — see the module docstring. One shell, one check.
                joined = "\n".join(e for e in entries if isinstance(e, str))
                if not joined.strip():
                    continue
                for line in _findings(joined):
                    total.append(f"{path.relative_to(root)}::{job}::{key}  {line}")

    for entry in total:
        print(f"  {entry}")

    n = len(total)
    if n > BASELINE:
        print(
            f"\nshellcheck_ci: {n} findings, baseline {BASELINE} — "
            f"{n - BASELINE} new. Fix them, or justify raising BASELINE.",
            file=sys.stderr,
        )
        return 1

    print(f"\nshellcheck_ci: {n} findings, baseline {BASELINE} — OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
