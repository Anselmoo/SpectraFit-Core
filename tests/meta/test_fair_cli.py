"""Tests for `scripts/fair.py` — the FAIR gates over `reproducibility/`.

Nothing covered the checksum manifest, the RO-Crate or the data registry before
this file existed, which is how the three encodings of "this file has this
digest" were free to disagree indefinitely.

The tests below deliberately exercise the LIVE tree rather than a fixture for
the agreement checks: a fixture would prove the comparison logic works while
saying nothing about whether the committed artifacts actually agree, and the
latter is the property CI needs.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "fair.py"
EVIDENCE = REPO / "reproducibility"

sys.path.insert(0, str(REPO / "scripts"))

import fair  # ty: ignore[unresolved-import]
from fair import (  # ty: ignore[unresolved-import]
    ASSETS,
    MANIFEST,
    REQUIRED_ASSET_FIELDS,
    SOURCE_TREES,
    _load_assets,
    _read_manifest,
    _sha256,
    build_crate,
)


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


# --- the three gates pass on the committed tree ---------------------------
@pytest.mark.parametrize(
    "args",
    [("checksums", "--check"), ("asset",), ("bundle", "--verify")],
)
def test_gate_passes_on_the_committed_tree(args: tuple[str, ...]) -> None:
    result = _run(*args)
    assert result.returncode == 0, result.stdout + result.stderr


# --- manifest ------------------------------------------------------------
def test_manifest_describes_every_covered_file() -> None:
    """Every file under a source tree is listed, and nothing else is."""
    recorded = set(_read_manifest(MANIFEST))
    on_disk = {
        p.relative_to(EVIDENCE).as_posix()
        for tree in SOURCE_TREES
        for p in (EVIDENCE / tree).rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc", ".log"}
    }
    assert recorded == on_disk


def test_manifest_digests_match_the_files() -> None:
    for rel, digest in _read_manifest(MANIFEST).items():
        assert _sha256(EVIDENCE / rel) == digest, rel


@pytest.mark.parametrize("subtree", ["ladder", "seed-sweep"])
def test_sub_manifest_agrees_with_the_root_manifest(subtree: str) -> None:
    """The failure this tool was written to catch: two coordinate systems drifting.

    Each subtree records digests relative to itself; the root manifest records
    the same files relative to `reproducibility/`. Nothing compared them before.
    """
    root = _read_manifest(MANIFEST)
    nested = _read_manifest(EVIDENCE / subtree / "checksums.sha256")
    for rel, digest in nested.items():
        key = f"{subtree}/{rel}"
        assert key in root, f"{key} is in the sub-manifest but not the root manifest"
        assert root[key] == digest, f"{key} digest disagrees between the two manifests"


# --- RO-Crate ------------------------------------------------------------
@pytest.mark.parametrize(
    "crate_rel",
    [
        "ro-crate-metadata.json",
        "ladder/ro-crate-metadata.json",
        "seed-sweep/ro-crate-metadata.json",
    ],
)
def test_crate_file_digests_match_the_files(crate_rel: str) -> None:
    crate = EVIDENCE / crate_rel
    for node in json.loads(crate.read_text())["@graph"]:
        if node.get("@type") != "File" or "sha256" not in node:
            continue
        target = crate.parent / node["@id"]
        assert target.is_file(), f"{crate_rel} describes a missing file: {node['@id']}"
        assert _sha256(target) == node["sha256"], f"{crate_rel}: {node['@id']}"


def test_crate_conforms_to_the_committed_reference_shape() -> None:
    """The two sub-crates are the only specification the retired writer left."""
    reference = json.loads((EVIDENCE / "ladder" / "ro-crate-metadata.json").read_text())
    built = build_crate()
    assert built["@context"] == reference["@context"]

    descriptor = built["@graph"][0]
    assert descriptor["@id"] == "ro-crate-metadata.json"
    assert descriptor["@type"] == "CreativeWork"
    assert descriptor["conformsTo"] == {"@id": "https://w3id.org/ro/crate/1.1"}
    assert descriptor["about"] == {"@id": "./"}

    dataset = built["@graph"][1]
    assert dataset["@id"] == "./"
    assert dataset["@type"] == "Dataset"
    for key in ("name", "description", "license", "datePublished", "version", "hasPart"):
        assert key in dataset, f"Dataset node is missing {key!r}"


@pytest.mark.parametrize(
    "crate_rel",
    [
        "ro-crate-metadata.json",
        "ladder/ro-crate-metadata.json",
        "seed-sweep/ro-crate-metadata.json",
    ],
)
def test_crate_carries_an_author_with_an_orcid(crate_rel: str) -> None:
    """Every crate -- the generated root and both committed sub-crates -- names its author.

    The two sub-crates used to carry no ``author`` at all (the retired writer
    that produced them never populated it); both are now hand-filled with the
    same ``CITATION.cff``-derived Person node the root crate builds, so this
    gap is closed. The root crate is checked against a fresh ``build_crate()``;
    the two sub-crates are static and are checked against the committed file.
    """
    if crate_rel == "ro-crate-metadata.json":
        author = build_crate()["@graph"][1]["author"]
    else:
        crate = json.loads((EVIDENCE / crate_rel).read_text())
        author = crate["@graph"][1]["author"]
    assert author["@type"] == "Person"
    assert author["@id"].startswith("https://orcid.org/")


# --- datePublished ---------------------------------------------------------
def test_date_published_falls_back_to_the_frozen_pin_without_date_released(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No ``date-released`` in CITATION.cff -> the pinned constant, not today's date."""
    monkeypatch.setattr(fair, "_load_citation", lambda: {"authors": []})
    assert fair._date_published() == fair.EVIDENCE_FROZEN


def test_date_published_prefers_date_released_when_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``date-released`` wins over the pinned fallback once the file sets it."""
    monkeypatch.setattr(fair, "_load_citation", lambda: {"date-released": "2027-01-15"})
    assert fair._date_published() == "2027-01-15"


def test_date_published_normalises_a_yaml_date_object(monkeypatch: pytest.MonkeyPatch) -> None:
    """PyYAML parses an unquoted ``YYYY-MM-DD`` scalar as ``datetime.date``, not ``str``."""
    monkeypatch.setattr(fair, "_load_citation", lambda: {"date-released": date(2027, 1, 15)})
    assert fair._date_published() == "2027-01-15"


def test_build_crate_never_shells_out_to_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """``datePublished`` used to come from ``git log``; it must not any more.

    A crate built before its own commit exists and verified after it drifts on
    every commit touching the evidence, and epoch-falls-back on a shallow
    clone. Asserting no `subprocess.run` call happens during `build_crate()`
    pins that the fix is structural, not incidental.
    """

    def _forbidden(*_args: object, **_kwargs: object) -> None:
        msg = "build_crate() must not invoke subprocess.run (no git calls)"
        raise AssertionError(msg)

    monkeypatch.setattr(fair.subprocess, "run", _forbidden)
    build_crate()


def test_crate_does_not_describe_itself_or_the_manifest() -> None:
    """A crate and a manifest each carrying the other's digest is unsatisfiable.

    The self-descriptor node names the crate, so the check is specifically that
    no ``File`` node does -- the descriptor carries no digest.
    """
    graph = build_crate()["@graph"]
    described = {n["@id"] for n in graph if n.get("@type") == "File"}
    assert "ro-crate-metadata.json" not in described
    assert "checksums.sha256" not in described
    parts = {p["@id"] for p in graph[1]["hasPart"]}
    assert "ro-crate-metadata.json" not in parts
    assert "checksums.sha256" not in parts


def test_crate_is_deterministic() -> None:
    assert build_crate() == build_crate()


# --- data assets ---------------------------------------------------------
def test_every_asset_carries_complete_provenance() -> None:
    """A vendored dataset without a licence and a citation cannot be reused."""
    assets = _load_assets()
    assert assets, f"{ASSETS} registers no assets"
    for entry in assets:
        for field in REQUIRED_ASSET_FIELDS:
            assert entry.get(field), f"{entry.get('name')}: missing {field!r}"
        assert (REPO / entry["license_notice"]).is_file()


def test_asset_digests_and_sizes_match_disk() -> None:
    for entry in _load_assets():
        path = REPO / entry["path"]
        assert path.is_file(), entry["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == entry["sha256"]
        assert path.stat().st_size == entry["bytes"]


def test_a_tampered_asset_is_caught(tmp_path: Path) -> None:
    """The gate must fail on a changed byte, not merely on a missing file."""
    entry = _load_assets()[0]
    original = (REPO / entry["path"]).read_bytes()
    try:
        (REPO / entry["path"]).write_bytes(original + b"\n# tampered\n")
        assert _run("asset").returncode == 1
    finally:
        (REPO / entry["path"]).write_bytes(original)
    assert _run("asset").returncode == 0
