#!/usr/bin/env python3
"""Verify the vendored third-party web assets against scripts/vendored_assets.toml.

Three libraries are checked into `docs/` so the published site makes no
third-party CDN request: KaTeX, GLightbox and mermaid. Before this check, the
only record of which version each one was lived in prose comments, and nothing
verified the bytes on disk. That is a worse position than referencing a CDN: you
cannot tell what the file is, whether it was modified, or whether it carries a
known vulnerability.

Default mode is offline and fast — it hashes each file and compares against the
manifest, so CI never depends on npm being reachable:

    uv run python scripts/check_vendored_assets.py

    --update           rewrite the manifest hashes from what is on disk, for a
                       deliberate upgrade. Review the diff; an unexpected hash
                       change is exactly what this file exists to surface.
    --check-upstream   re-fetch each pinned URL and compare. Opt-in, and it
                       WARNS rather than fails: a new upstream release is
                       information, not a reason to break an unrelated build.

Exit codes: 0 all good, 1 a hash mismatch or a missing file.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = Path(__file__).resolve().parent / "vendored_assets.toml"
TIMEOUT_S = 30


def sha256(path: Path) -> str:
    """Return the hex SHA-256 of a file's bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_assets() -> list[dict]:
    """Return the declared assets from the manifest."""
    return tomllib.loads(MANIFEST.read_text())["asset"]


def check(assets: list[dict]) -> int:
    """Hash every vendored file and compare with the manifest."""
    failures = 0
    for a in assets:
        path = REPO / a["path"]
        if not path.exists():
            print(f"  MISSING  {a['name']:20s} {a['path']}")
            failures += 1
            continue
        actual = sha256(path)
        if actual != a["sha256"]:
            print(f"  MISMATCH {a['name']:20s} {a['path']}")
            print(f"           manifest {a['sha256']}")
            print(f"           on disk  {actual}")
            failures += 1
            continue
        size_mb = path.stat().st_size / 1_048_576
        verified = "" if a.get("version_verified") else "  (version unverified)"
        print(f"  ok       {a['name']:20s} {a['version']:10s} {size_mb:5.2f} MB{verified}")

        lic = a.get("license")
        if lic and not (REPO / lic).exists():
            print(f"           WARNING declared licence file is missing: {lic}")
        elif not lic:
            # Not a failure: a missing licence file does not break the build.
            # It is still a real gap for a redistributed third-party asset, so
            # it is said out loud on every run rather than filed and forgotten.
            print(f"           WARNING no licence vendored alongside {a['name']}")
    return failures


def check_upstream(assets: list[dict]) -> None:
    """Re-fetch each pinned URL and report drift. Never fails the run."""
    print("\nupstream (opt-in; warnings only):")
    for a in assets:
        url = a.get("url")
        if not url:
            continue
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT_S) as fh:
                remote = hashlib.sha256(fh.read()).hexdigest()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            # Explicitly not a failure. An unreachable registry says nothing
            # about the correctness of the bytes already on disk.
            print(f"  ?        {a['name']:20s} unreachable ({type(exc).__name__})")
            continue
        # Read the version from the manifest, not by slicing the URL. The old
        # `url.rsplit("/", 3)[0].rsplit("@", 1)[-1]` assumed a fixed path depth
        # and silently produced "https://unpkg.com" for any asset whose URL had
        # one segment fewer — mermaid and glightbox both did, so two of six
        # assets reported a hostname where a version belonged.
        pinned_version = a.get("version", "?")
        if remote == a["sha256"]:
            if a.get("modified"):
                # Declared a derivative, yet byte-identical to upstream. Either
                # the local edit was lost in a re-download, or `modified` is
                # stale. Both are worth saying out loud — a silent "ok" here
                # would hide the loss of a deliberate change.
                print(
                    f"  RECHECK  {a['name']:20s} declared modified = true, but matches upstream exactly",
                )
                print("           the local edit may have been reverted by a re-download")
            else:
                print(f"  ok       {a['name']:20s} matches {pinned_version}")
        elif a.get("modified"):
            # EXPECTED. This asset is a documented derivative of the pinned
            # release, so differing from upstream is the correct outcome, not
            # drift. Reporting it as DIFFERS trains readers to ignore the
            # signal, which is exactly how a real drift gets missed.
            print(f"  ok       {a['name']:20s} derivative of {pinned_version}, differs by design")
        else:
            note = "" if a.get("version_verified") else "  — version was already unverified"
            print(
                f"  DIFFERS  {a['name']:20s} pinned URL no longer matches the vendored file{note}",
            )
            print(f"           {url}")


def update(assets: list[dict]) -> None:
    """Rewrite manifest hashes from the files currently on disk."""
    text = MANIFEST.read_text()
    changed = 0
    for a in assets:
        path = REPO / a["path"]
        if not path.exists():
            print(f"  skip {a['name']}: {a['path']} does not exist")
            continue
        actual = sha256(path)
        if actual == a["sha256"]:
            continue
        # Replace only this asset's hash line — matching on the old value keeps
        # the edit unambiguous even when two assets share a version string.
        text = re.sub(
            rf'^sha256 = "{re.escape(a["sha256"])}"$',
            f'sha256 = "{actual}"',
            text,
            count=1,
            flags=re.MULTILINE,
        )
        print(f"  updated {a['name']:20s} {a['sha256'][:12]} -> {actual[:12]}")
        changed += 1
    if changed:
        MANIFEST.write_text(text)
        print(f"\n{changed} hash(es) rewritten — review the diff before committing")
    else:
        print("  nothing to update; every hash already matches")


def main() -> int:
    """Verify, update, or probe upstream."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--update", action="store_true", help="rewrite hashes from disk")
    ap.add_argument("--check-upstream", action="store_true", help="re-fetch pinned URLs")
    args = ap.parse_args()

    assets = load_assets()
    if args.update:
        update(assets)
        return 0

    print(f"vendored assets ({len(assets)} declared in {MANIFEST.name}):")
    failures = check(assets)
    if args.check_upstream:
        check_upstream(assets)

    if failures:
        print(
            f"\n{failures} problem(s). If a change was deliberate, re-run with "
            "--update and review the diff.",
            file=sys.stderr,
        )
        return 1
    print("\nall vendored assets match the manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
