#!/usr/bin/env python3
"""FAIR tooling for the published evidence under ``reproducibility/``.

``reproducibility/`` holds ~16 MB of measurement artifacts that the
documentation and ``LIMITATIONS.md`` cite as evidence for specific claims, plus
third-party measured data vendored from outside this project. Evidence a reader
is invited to verify has to be verifiable, and data they are invited to reuse
has to say who owns it. This command enforces both.

    uv run poe fair checksums [--check]   whole-tree sha256 manifest
    uv run poe fair asset [--update]      third-party data provenance + digests
    uv run poe fair bundle [--verify]     RO-Crate 1.1 describing the tree

WHY ONE COMMAND. Before this existed the same fact -- "this file has this
digest" -- was recorded in three mutually incompatible encodings that never met:
``checksums.sha256`` (three files, each relative to a different directory),
``sha256`` fields on RO-Crate ``File`` nodes, and ``artifacts[]`` entries inside
per-rung ``provenance.json``. Nothing cross-validated any of them, so a
sub-manifest could disagree with the root manifest indefinitely and no check
would notice. ``checksums --check`` now reconciles the first two; the third is
written by tooling that no longer lives in this repository and is left alone.

ORDER MATTERS when regenerating. ``bundle`` writes the crate, which the manifest
then covers, so run ``bundle`` before ``checksums``. The crate deliberately does
NOT describe itself or ``checksums.sha256`` -- a crate carrying the digest of a
manifest that carries the digest of the crate cannot be satisfied by any pair of
files.

This absorbs the standalone checksum tooling that used to live elsewhere. The
original FAIR-package builder and RO-Crate writer that produced the two
committed sub-crates are not part of this repository; ``bundle`` is a
reimplementation against those crates as its specification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "reproducibility"
MANIFEST = EVIDENCE / "checksums.sha256"
ASSETS = EVIDENCE / "assets.toml"
CRATE = EVIDENCE / "ro-crate-metadata.json"
CITATION = ROOT / "CITATION.cff"

# Fallback `datePublished` while CITATION.cff carries no `date-released` (see
# that file's own comment on why the line is absent until 0.1.0 is tagged).
# Bump this by hand, deliberately, when the evidence tree materially changes —
# never derive it from `git log`, which drifts on every commit that touches
# `reproducibility/` and epoch-falls-back on a shallow clone (see
# `_date_published`). Superseded automatically once `date-released` is set.
EVIDENCE_FROZEN = "2026-09-22"

# Every subtree the manifest describes. Named explicitly rather than globbed, so
# adding a directory is a decision someone records here.
SOURCE_TREES: tuple[str, ...] = (
    "ladder",
    "seed-sweep",
    "figures",
    "nist_unimplemented",
    "spectra",
)

# Sub-manifests that must agree with the root one, keyed by their subtree.
NESTED_MANIFESTS: tuple[str, ...] = ("ladder", "seed-sweep")

# Build detritus that is never an input to anything. `.log` is here because the
# per-seed `run.log` files are a human-readable rendering of numbers the
# `provenance.json` beside them already carries at full precision.
SKIP_DIR_NAMES = frozenset({"__pycache__", ".ipynb_checkpoints", ".pytest_cache"})
SKIP_FILE_NAMES = frozenset({".DS_Store", ".gitkeep"})
SKIP_SUFFIXES = frozenset({".pyc", ".pyo", ".log"})

# Provenance fields an asset may not omit. A vendored dataset without these is
# one nobody can safely reuse, which defeats the point of publishing it.
REQUIRED_ASSET_FIELDS = ("name", "path", "sha256", "url", "license", "citation")

MEDIA_TYPES = {
    ".json": "application/json",
    ".md": "text/markdown",
    ".py": "text/x-python",
    ".tex": "application/x-tex",
    ".png": "image/png",
    ".pdf": "application/pdf",
    ".toml": "application/toml",
    ".sha256": "text/plain",
    ".msa": "text/plain",
    ".txt": "text/plain",
    ".csv": "text/csv",
}


# --------------------------------------------------------------------------
# shared helpers
# --------------------------------------------------------------------------
def _skipped(path: Path) -> bool:
    """Return True for build detritus that is never an input to anything."""
    return (
        any(part in SKIP_DIR_NAMES for part in path.parts)
        or path.name in SKIP_FILE_NAMES
        or path.suffix in SKIP_SUFFIXES
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _covered() -> list[Path]:
    """Every file the manifest should describe, sorted, manifest itself excluded."""
    out: list[Path] = []
    for src_rel in SOURCE_TREES:
        src = EVIDENCE / src_rel
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
    tool was written to stop, so it is an error here and not a warning.
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


def _read_manifest(path: Path) -> dict[str, str]:
    """Parse a ``<digest>  <relative path>`` manifest into ``{path: digest}``."""
    recorded: dict[str, str] = {}
    for line in path.read_text().splitlines():
        digest, _, name = line.partition("  ")
        if name:
            recorded[name.strip()] = digest
    return recorded


def _report(label: str, items: list[str]) -> None:
    if not items:
        return
    print(f"  {len(items)} file(s) {label}:")
    for item in items[:12]:
        print(f"    {item}")
    if len(items) > 12:
        print(f"    ... and {len(items) - 12} more")


# --------------------------------------------------------------------------
# fair checksums
# --------------------------------------------------------------------------
def _nested_disagreements(recorded: dict[str, str]) -> list[str]:
    """Entries where a sub-manifest and the root manifest disagree.

    Each subtree keeps its own ``checksums.sha256`` relative to itself, while the
    root manifest records the same files relative to ``reproducibility/``. Two
    coordinate systems describing one set of bytes will drift unless something
    compares them; nothing did before this.
    """
    problems: list[str] = []
    for subtree in NESTED_MANIFESTS:
        nested = EVIDENCE / subtree / "checksums.sha256"
        if not nested.is_file():
            problems.append(f"{subtree}/checksums.sha256 is missing")
            continue
        for rel, digest in _read_manifest(nested).items():
            key = f"{subtree}/{rel}"
            where = f"{subtree}/checksums.sha256"
            if key not in recorded:
                problems.append(f"{key} listed in {where} but not in the root manifest")
            elif recorded[key] != digest:
                problems.append(f"{key} digest disagrees between {where} and the root manifest")
    return problems


def _crate_disagreements() -> list[str]:
    """Entries where an RO-Crate ``File`` node's ``sha256`` is not the file's."""
    problems: list[str] = []
    crates = [EVIDENCE / s / "ro-crate-metadata.json" for s in NESTED_MANIFESTS]
    crates.append(CRATE)
    for crate in crates:
        if not crate.is_file():
            continue
        graph = json.loads(crate.read_text())["@graph"]
        for node in graph:
            if node.get("@type") != "File" or "sha256" not in node:
                continue
            target = crate.parent / node["@id"]
            rel = target.relative_to(EVIDENCE).as_posix()
            if not target.is_file():
                problems.append(f"{rel} described by {crate.name} but absent from the tree")
            elif _sha256(target) != node["sha256"]:
                problems.append(f"{rel} digest disagrees between {crate.name} and the file")
    return problems


def checksums_check() -> int:
    """Verify the manifest against the tree. Return a process exit code."""
    if not MANIFEST.is_file():
        print(f"error: {MANIFEST.relative_to(ROOT)} does not exist; run without --check")
        return 1

    recorded = _read_manifest(MANIFEST)
    files = _covered()
    present = {p.relative_to(EVIDENCE).as_posix(): p for p in files}

    missing = sorted(set(recorded) - set(present))
    unlisted = sorted(set(present) - set(recorded))
    changed = sorted(
        name for name, p in present.items() if name in recorded and _sha256(p) != recorded[name]
    )
    loose = _untracked(files)
    nested = _nested_disagreements(recorded)
    crates = _crate_disagreements()

    _report("listed but absent from the tree", missing)
    _report("present but not listed", unlisted)
    _report("listed with a different digest", changed)
    _report("not tracked by git", [str(p.relative_to(ROOT)) for p in loose])
    _report("disagreeing with a sub-manifest", nested)
    _report("disagreeing with an RO-Crate", crates)

    if missing or unlisted or changed or loose or nested or crates:
        print("\nfair checksums: DRIFT — regenerate with")
        print("  uv run poe fair bundle && uv run poe fair checksums")
        return 1

    print(
        f"fair checksums: {len(recorded)} file(s) verified, all tracked, none unlisted; "
        f"{len(NESTED_MANIFESTS)} sub-manifest(s) and every RO-Crate digest agree",
    )
    return 0


def checksums_write() -> int:
    """Regenerate the manifest. Return a process exit code."""
    files = _covered()
    loose = _untracked(files)
    if loose:
        print(f"error: {len(loose)} file(s) are not tracked by git:")
        for p in loose[:12]:
            print(f"    {p.relative_to(ROOT)}")
        return 1
    lines = [f"{_sha256(p)}  {p.relative_to(EVIDENCE).as_posix()}" for p in files]
    MANIFEST.write_text("\n".join(lines) + "\n")
    print(f"wrote {MANIFEST.relative_to(ROOT)}  ({len(files)} files)")
    return 0


# --------------------------------------------------------------------------
# fair asset
# --------------------------------------------------------------------------
def _load_assets() -> list[dict[str, Any]]:
    if not ASSETS.is_file():
        return []
    return tomllib.loads(ASSETS.read_text()).get("asset", [])


def asset_check() -> int:
    """Verify every vendored data asset's digest and provenance completeness."""
    assets = _load_assets()
    if not assets:
        print(f"fair asset: no assets registered in {ASSETS.relative_to(ROOT)}")
        return 0

    problems: list[str] = []
    for entry in assets:
        name = entry.get("name", "<unnamed>")
        for field in REQUIRED_ASSET_FIELDS:
            if not entry.get(field):
                problems.append(f"{name}: missing required provenance field {field!r}")
        rel = entry.get("path")
        if not rel:
            continue
        path = ROOT / rel
        if not path.is_file():
            problems.append(f"{name}: {rel} is registered but absent")
            continue
        actual = _sha256(path)
        if actual != entry.get("sha256"):
            recorded_digest = entry.get("sha256")
            problems.append(f"{name}: {rel} digest is {actual}, registry says {recorded_digest}")
        size = entry.get("bytes")
        if size is not None and path.stat().st_size != size:
            problems.append(f"{name}: {rel} is {path.stat().st_size} bytes, registry says {size}")
        notice = entry.get("license_notice")
        if notice and not (ROOT / notice).is_file():
            problems.append(f"{name}: license_notice {notice} does not exist")

    if problems:
        print(f"fair asset: {len(problems)} problem(s)")
        for p in problems:
            print(f"    {p}")
        print("\nregenerate digests with: uv run poe fair asset --update")
        return 1

    print(f"fair asset: {len(assets)} asset(s) verified — digests, sizes and provenance complete")
    return 0


def asset_update() -> int:
    """Rewrite recorded digests and sizes from what is now on disk."""
    text = ASSETS.read_text()
    changes = 0
    for entry in _load_assets():
        path = ROOT / entry["path"]
        if not path.is_file():
            print(f"error: {entry['path']} is registered but absent")
            return 1
        digest, size = _sha256(path), path.stat().st_size
        if entry.get("sha256") != digest:
            text = text.replace(f'sha256 = "{entry["sha256"]}"', f'sha256 = "{digest}"')
            changes += 1
        if entry.get("bytes") is not None and entry["bytes"] != size:
            text = text.replace(f"bytes = {entry['bytes']}", f"bytes = {size}")
            changes += 1
    ASSETS.write_text(text)
    print(f"fair asset: {changes} field(s) updated in {ASSETS.relative_to(ROOT)}")
    return 0


# --------------------------------------------------------------------------
# fair bundle
# --------------------------------------------------------------------------
def _load_citation() -> dict[str, Any]:
    """Parse CITATION.cff once; shared by the author and the date lookups.

    Imported here, not at module scope: only this subcommand needs PyYAML, so
    `checksums` and `asset` stay runnable without it.
    """
    import yaml

    return yaml.safe_load(CITATION.read_text())


def _author_from_citation() -> dict[str, Any]:
    """Read the author identity from CITATION.cff rather than hardcoding it.

    `rrt` already keeps CITATION.cff in version-sync (`[[tool.rrt.version_targets]]`),
    so deriving the crate's author from it keeps one source of truth for identity
    exactly as there is one for version. The two committed sub-crates carry no
    author at all, which is the gap this closes.
    """
    cff = _load_citation()
    first = cff["authors"][0]
    name = f"{first['given-names']} {first['family-names']}"
    node: dict[str, Any] = {"@type": "Person", "name": name}
    if first.get("orcid"):
        node["@id"] = first["orcid"]
    return node


def _date_published() -> str:
    """The crate's `datePublished`: CITATION.cff's `date-released` if set, else a pin.

    This used to shell out to `git log -1` for the newest commit touching
    `reproducibility/`. That looked principled but was not stable: `bundle`
    generates the crate BEFORE its own commit exists, so the value it writes
    and the value `bundle --verify` reads back afterwards can legitimately
    differ, and a shallow clone (GitHub Actions' default checkout) sees no
    history at all and silently falls back to the Unix epoch. None of that is
    a property of the evidence -- it is a property of when and how the
    repository happened to be cloned, which is exactly what a citable date
    must not depend on. No `git` call is made here.

    `CITATION.cff`'s `date-released` becomes authoritative the moment 0.1.0 is
    actually tagged (see that file's own comment on why it is absent today).
    Until then this returns `EVIDENCE_FROZEN`, a constant bumped by hand,
    deliberately, when the evidence tree materially changes.
    """
    released = _load_citation().get("date-released")
    if released:
        # PyYAML parses an unquoted YYYY-MM-DD scalar as `datetime.date`, not
        # `str` -- CITATION.cff deliberately leaves it unquoted -- so normalise
        # either representation to the `YYYY-MM-DD` string RO-Crate expects.
        return released.isoformat() if hasattr(released, "isoformat") else str(released)
    return EVIDENCE_FROZEN


def _version() -> str:
    text = (ROOT / "pyproject.toml").read_text()
    return tomllib.loads(text)["project"]["version"]


def build_crate() -> dict[str, Any]:
    """Assemble the RO-Crate 1.1 graph describing ``reproducibility/``."""
    # The crate never describes itself or the manifest: each would have to carry
    # the other's digest, which no pair of files can satisfy.
    files = [p for p in _covered() if p not in {CRATE, MANIFEST}]
    assets = {ROOT / a["path"]: a for a in _load_assets()}

    parts = [{"@id": p.relative_to(EVIDENCE).as_posix()} for p in files]
    graph: list[dict[str, Any]] = [
        {
            "@id": "ro-crate-metadata.json",
            "@type": "CreativeWork",
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            "about": {"@id": "./"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "name": f"spectrafit-core published evidence — v{_version()}",
            "description": (
                "Measurement artifacts that spectrafit-core's documentation and "
                "LIMITATIONS.md cite as evidence: the reps-ladder and seed-sweep "
                "benchmark records with their per-rung provenance, the figure "
                "scripts and rendered figures derived from them, the NIST StRD "
                "coverage record, and third-party measured spectra vendored under "
                "their own licences. Digests for every file are also recorded in "
                "checksums.sha256; neither that file nor this one describes the "
                "other, so that the pair is satisfiable."
            ),
            "license": {"@id": "https://spdx.org/licenses/MIT.html"},
            "author": _author_from_citation(),
            "datePublished": _date_published(),
            "version": _version(),
            "url": "https://github.com/Anselmoo/SpectraFit-Core",
            "keywords": [
                "curve fitting",
                "benchmark",
                "reproducibility",
                "NIST StRD",
                "electron energy-loss spectroscopy",
            ],
            "measurementTechnique": "cross-backend nonlinear least-squares benchmark",
            "hasPart": parts,
        },
    ]

    for path in files:
        rel = path.relative_to(EVIDENCE).as_posix()
        node: dict[str, Any] = {
            "@id": rel,
            "@type": "File",
            "name": path.name,
            "encodingFormat": MEDIA_TYPES.get(path.suffix, "application/octet-stream"),
            "contentSize": path.stat().st_size,
            "sha256": _sha256(path),
        }
        # A vendored asset carries its OWN licence, not the crate's MIT. Saying
        # so per-file is the difference between a reader knowing what they may
        # reuse and having to guess.
        asset = assets.get(path)
        if asset:
            node["license"] = {"@id": asset["license_url"]}
            node["citation"] = asset["citation"]
            if asset.get("contributor"):
                node["contributor"] = {"@type": "Person", "name": asset["contributor"]}
        graph.append(node)

    for asset in assets.values():
        graph.append(
            {
                "@id": asset["license_url"],
                "@type": "CreativeWork",
                "name": asset["license"],
                "description": f"Licence governing {asset['name']}; see {asset['license_notice']}.",
            },
        )

    return {"@context": "https://w3id.org/ro/crate/1.1/context", "@graph": graph}


def _crate_text() -> str:
    return json.dumps(build_crate(), indent=2, ensure_ascii=False) + "\n"


def bundle_write() -> int:
    """Write the crate. Return a process exit code."""
    CRATE.write_text(_crate_text())
    n = len(json.loads(CRATE.read_text())["@graph"])
    print(f"wrote {CRATE.relative_to(ROOT)}  ({n} graph entries)")
    return 0


def bundle_verify() -> int:
    """Rebuild the crate in memory and compare against the committed one."""
    if not CRATE.is_file():
        print(f"error: {CRATE.relative_to(ROOT)} does not exist; run without --verify")
        return 1
    if CRATE.read_text() == _crate_text():
        print(f"fair bundle: {CRATE.relative_to(ROOT)} is byte-identical to a fresh rebuild")
        return 0
    print(f"fair bundle: DRIFT — {CRATE.relative_to(ROOT)} differs from a fresh rebuild")
    print("  regenerate with: uv run poe fair bundle")
    return 1


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    """Dispatch a FAIR subcommand. Return a process exit code."""
    parser = argparse.ArgumentParser(prog="fair", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_sums = sub.add_parser("checksums", help="whole-tree sha256 manifest")
    p_sums.add_argument("--check", action="store_true", help="verify instead of regenerating")

    p_asset = sub.add_parser("asset", help="third-party data provenance and digests")
    p_asset.add_argument("--update", action="store_true", help="rewrite digests from disk")

    p_bundle = sub.add_parser("bundle", help="RO-Crate 1.1 describing the evidence tree")
    p_bundle.add_argument("--verify", action="store_true", help="compare against a fresh rebuild")

    args = parser.parse_args(argv)
    match args.command:
        case "checksums":
            return checksums_check() if args.check else checksums_write()
        case "asset":
            return asset_update() if args.update else asset_check()
        case "bundle":
            return bundle_verify() if args.verify else bundle_write()
        case _:  # pragma: no cover - argparse rejects anything else
            parser.error(f"unknown command {args.command!r}")
            return 2


if __name__ == "__main__":
    sys.exit(main())
