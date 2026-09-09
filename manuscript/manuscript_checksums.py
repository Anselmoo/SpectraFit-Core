#!/usr/bin/env python3
"""One integrity manifest over every measured artifact the paper cites.

Why this exists
---------------
`manuscript/examples/` held two hand-written manifests and two directories with
none at all:

    ladder/checksums.sha256        19 entries
    seed-sweep/checksums.sha256   152 entries
    figures/                      no manifest
    fecl4/                        no manifest
    nist_unimplemented/           no manifest

`figures/` and `fecl4/` are where `data_availability.md` says the primary
artifacts live -- `bench_summary.json`, `nist_table2.json`, `param_agreement.json`,
`audit_bias.json`, `se_timer_bias.json`, `fecl4_fit_results.json` -- so the two
directories a reader most needs to check were the two nobody could.

Worse, the two manifests that did exist were committed once by hand and never
regenerated. One of them drifted: it listed 50 `run.log` files that `.gitignore`
excludes, so `sha256sum -c` from a clean clone reported 50 missing files while
the README claimed both manifests "verify clean". A hand-maintained manifest is a
claim about integrity that nothing checks, which is the one kind of claim this
project does not make anywhere else.

So: one manifest, generated, with a `--check` mode a gate can run.

What it covers
--------------
Every file under the same source trees `build_fair_package.py` packages,
under the same skip rules -- imported from that module rather than restated, so
the manifest and the deposit cannot drift apart. Paths are relative to
`manuscript/examples/`.

The per-directory manifests stay. They are not redundant: `ladder/` and
`seed-sweep/` are each a self-contained RO-Crate describing one dataset, and a
crate that does not carry its own checksums stops being self-describing the
moment it is deposited on its own. This file is the belt over those braces, and
it hashes them too -- so editing a per-directory manifest without regenerating
this one is itself caught.

Usage
-----
    uv run python manuscript checksums              # regenerate
    uv run python manuscript checksums --check        # verify, exit 1 on drift
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from pathlib import Path

# `build_fair_package` is a sibling in this directory. The import is the point:
# SOURCE_TREES and the skip rules are what decide which files count as an input,
# and a second copy of that decision here would be free to drift from the deposit
# it is supposed to describe.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_fair_package import ROOT, SOURCE_TREES, _skipped

BASE = ROOT / "manuscript" / "examples"
MANIFEST = BASE / "checksums.sha256"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _covered() -> list[Path]:
    """Every file the manifest should describe, sorted, manifest itself excluded."""
    out: list[Path] = []
    for src_rel, _ in SOURCE_TREES:
        src = ROOT / src_rel
        if not src.is_dir():
            continue
        out.extend(
            p
            for p in src.rglob("*")
            if p.is_file() and not _skipped(p.relative_to(src)) and p != MANIFEST
        )
    return sorted(out)


def _untracked(paths: list[Path]) -> list[Path]:
    """Which of `paths` git does not track.

    A manifest entry for a file no clean clone receives is exactly the drift this
    script was written to stop, so it is an error here and not a warning.
    """
    if not paths:
        return []
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "-z", "--", *[str(p) for p in paths]],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    tracked = {ROOT / p for p in proc.stdout.split("\0") if p}
    return [p for p in paths if p.resolve() not in tracked]


def _lines(files: list[Path]) -> list[str]:
    return [f"{_sha256(p)}  {p.relative_to(BASE).as_posix()}" for p in files]


def check() -> int:
    """Verify the manifest against the tree. Return a process exit code."""
    if not MANIFEST.is_file():
        print(f"error: {MANIFEST.relative_to(ROOT)} does not exist; run without --check")
        return 1

    recorded = {}
    for line in MANIFEST.read_text().splitlines():
        digest, _, name = line.partition("  ")
        if name:
            recorded[name.strip()] = digest

    files = _covered()
    present = {p.relative_to(BASE).as_posix(): p for p in files}

    missing = sorted(set(recorded) - set(present))
    unlisted = sorted(set(present) - set(recorded))
    changed = sorted(
        name for name, p in present.items() if name in recorded and _sha256(p) != recorded[name]
    )
    loose = _untracked(files)

    for label, items in (
        ("listed but absent from the tree", missing),
        ("present but not listed", unlisted),
        ("listed with a different digest", changed),
        ("not tracked by git", [str(p.relative_to(ROOT)) for p in loose]),
    ):
        if items:
            print(f"  {len(items)} file(s) {label}:")
            for item in items[:12]:
                print(f"    {item}")
            if len(items) > 12:
                print(f"    ... and {len(items) - 12} more")

    if missing or unlisted or changed or loose:
        print("\nmanuscript checksums: DRIFT — regenerate with")
        print("  uv run python manuscript checksums")
        return 1

    print(f"manuscript checksums: {len(recorded)} file(s) verified, all tracked, none unlisted")
    return 0


def write() -> int:
    """Regenerate the manifest. Return a process exit code."""
    files = _covered()
    loose = _untracked(files)
    if loose:
        print(f"error: {len(loose)} covered file(s) are not tracked by git:")
        for path in loose[:12]:
            print(f"    {path.relative_to(ROOT)}")
        print("    Commit them, or add them to build_fair_package's skip lists.")
        return 1
    MANIFEST.write_text("\n".join(_lines(files)) + "\n")
    print(f"wrote {MANIFEST.relative_to(ROOT)}  ({len(files)} files)")
    for src_rel, _ in SOURCE_TREES:
        n = sum(1 for p in files if str(p).startswith(str(ROOT / src_rel)))
        print(f"  {Path(src_rel).name:22s} {n:4d}")
    return 0


def main() -> int:
    """Parse arguments and dispatch to check or regenerate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="verify instead of regenerating")
    args = parser.parse_args()
    return check() if args.check else write()


if __name__ == "__main__":
    raise SystemExit(main())
