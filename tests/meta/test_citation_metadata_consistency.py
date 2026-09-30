"""Cross-check the four citation/packaging metadata files agree with each other.

``pyproject.toml`` (the canonical version, per
``docs/contributor-guide/project-configuration.md#versioning-rrt``),
``CITATION.cff``, ``codemeta.json`` and ``.zenodo.json`` each carry a copy of
overlapping facts -- version, license, the first author's ORCID, the
repository URL; ``CITATION.cff``, ``codemeta.json`` and the README badge also
carry the Zenodo concept DOI. ``rrt`` keeps the version in sync across the first three as
part of its tracked version targets, but nothing previously asserted the
values actually agree, or that ``.zenodo.json`` (untracked by ``rrt``, since
Zenodo's GitHub integration reads the version from the release tag, not from
this file) stays free of a stale, conflicting ``version`` key.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = REPO_ROOT / "pyproject.toml"
_CITATION = REPO_ROOT / "CITATION.cff"
_CODEMETA = REPO_ROOT / "codemeta.json"
_ZENODO = REPO_ROOT / ".zenodo.json"


def _pyproject() -> dict[str, Any]:
    return tomllib.loads(_PYPROJECT.read_text())["project"]


def _citation() -> dict[str, Any]:
    return yaml.safe_load(_CITATION.read_text())


def _codemeta() -> dict[str, Any]:
    return json.loads(_CODEMETA.read_text())


def _zenodo() -> dict[str, Any]:
    return json.loads(_ZENODO.read_text())


# ---------------------------------------------------------------------------
# Version
# ---------------------------------------------------------------------------


def test_version_agrees_across_pyproject_citation_codemeta() -> None:
    """The three ``rrt``-tracked version targets must carry the same string."""
    pyproject_version = _pyproject()["version"]
    citation_version = str(_citation()["version"])
    codemeta_version = _codemeta()["version"]

    assert citation_version == pyproject_version, (
        f"CITATION.cff version {citation_version!r} != pyproject.toml version {pyproject_version!r}"
    )
    assert codemeta_version == pyproject_version, (
        f"codemeta.json version {codemeta_version!r} != pyproject.toml version "
        f"{pyproject_version!r}"
    )


def test_zenodo_json_has_no_version_key() -> None:
    """``.zenodo.json`` must NOT carry a ``version``.

    For a GitHub-triggered Zenodo deposit, the version is taken from the
    GitHub Release tag, not from this file. A stale ``version`` key here would
    silently disagree with the tag the moment a release is cut without also
    touching this file.
    """
    assert "version" not in _zenodo(), (
        ".zenodo.json must not declare a 'version' key -- Zenodo's GitHub "
        "integration takes the version from the release tag"
    )


# ---------------------------------------------------------------------------
# License
# ---------------------------------------------------------------------------

# SPDX-style "MIT" plus the handful of shapes these particular files use for
# it: a plain string, an SPDX URL, or (pre-PEP 639) a `{text = "MIT"}` table.
_MIT_SPDX_URL = "https://spdx.org/licenses/MIT"


def test_license_is_mit_everywhere() -> None:
    pyproject_license = _pyproject()["license"]
    # PEP 639: license is now a plain SPDX expression string.
    assert pyproject_license == "MIT", (
        f"pyproject.toml [project.license] must be the PEP 639 SPDX string "
        f"'MIT', got {pyproject_license!r}"
    )

    citation_license = _citation()["license"]
    assert citation_license == "MIT", (
        f"CITATION.cff license must be 'MIT', got {citation_license!r}"
    )

    codemeta_license = _codemeta()["license"]
    assert codemeta_license == _MIT_SPDX_URL, (
        f"codemeta.json license must be the SPDX URL {_MIT_SPDX_URL!r}, got {codemeta_license!r}"
    )

    # Zenodo's licence vocabulary is lowercase-only: /api/vocabularies/licenses/mit
    # resolves, /MIT is a 404.
    zenodo_license = _zenodo()["license"]
    assert zenodo_license == "mit", f".zenodo.json license must be 'mit', got {zenodo_license!r}"


# ---------------------------------------------------------------------------
# First author ORCID
# ---------------------------------------------------------------------------


def _bare_orcid(value: str) -> str:
    """Strip an optional ``https://orcid.org/`` prefix, for comparison."""
    return value.removeprefix("https://orcid.org/")


def test_first_author_orcid_agrees_across_citation_codemeta_zenodo() -> None:
    citation_orcid = _bare_orcid(_citation()["authors"][0]["orcid"])

    codemeta_authors = _codemeta()["author"]
    codemeta_orcid = _bare_orcid(codemeta_authors[0]["identifier"])

    zenodo_orcid = _bare_orcid(_zenodo()["creators"][0]["orcid"])

    assert codemeta_orcid == citation_orcid, (
        f"codemeta.json first author ORCID {codemeta_orcid!r} != CITATION.cff {citation_orcid!r}"
    )
    assert zenodo_orcid == citation_orcid, (
        f".zenodo.json first creator ORCID {zenodo_orcid!r} != CITATION.cff {citation_orcid!r}"
    )


# ---------------------------------------------------------------------------
# Repository URL
# ---------------------------------------------------------------------------


def _normalize_repo_url(url: str) -> str:
    return url.rstrip("/").lower()


def test_repository_url_agrees_case_insensitively() -> None:
    pyproject_repo = _pyproject()["urls"]["Repository"]
    citation_repo = _citation()["repository-code"]
    codemeta_repo = _codemeta()["codeRepository"]

    normalized = {
        "pyproject.toml": _normalize_repo_url(pyproject_repo),
        "CITATION.cff": _normalize_repo_url(citation_repo),
        "codemeta.json": _normalize_repo_url(codemeta_repo),
    }
    distinct = set(normalized.values())
    assert len(distinct) == 1, f"repository URLs disagree (case-insensitively): {normalized}"


# ---------------------------------------------------------------------------
# Zenodo concept DOI
# ---------------------------------------------------------------------------

_README = REPO_ROOT / "README.md"
_DOI_PREFIX = "https://doi.org/"
_README_DOI_BADGE = re.compile(
    r"\[!\[DOI\]\(https://zenodo\.org/badge/DOI/(?P<badge>10\.5281/zenodo\.\d+)\.svg\)\]"
    r"\(https://doi\.org/(?P<link>10\.5281/zenodo\.\d+)\)",
)


def test_concept_doi_agrees_across_citation_codemeta_readme() -> None:
    """One concept DOI, cited the same way in CITATION.cff, codemeta.json and the README badge."""
    citation_dois = [
        i["value"] for i in _citation().get("identifiers", []) if i.get("type") == "doi"
    ]
    assert len(citation_dois) == 1, (
        f"CITATION.cff must list exactly one DOI identifier, got {citation_dois}"
    )
    concept_doi = citation_dois[0]

    top_level_doi = _citation().get("doi")
    assert top_level_doi == concept_doi, (
        f"CITATION.cff top-level doi {top_level_doi!r} != its DOI identifier {concept_doi!r}"
    )

    codemeta_id = _codemeta()["@id"]
    assert codemeta_id == _DOI_PREFIX + concept_doi, (
        f"codemeta.json @id {codemeta_id!r} != {_DOI_PREFIX + concept_doi!r} (CITATION.cff)"
    )

    badge = _README_DOI_BADGE.search(_README.read_text())
    assert badge, "README.md has no Zenodo DOI badge"
    assert badge["badge"] == badge["link"] == concept_doi, (
        f"README DOI badge ({badge['badge']}, link {badge['link']}) != {concept_doi} (CITATION.cff)"
    )


def test_citation_cites_the_software_until_an_article_is_accepted() -> None:
    """No ``preferred-citation`` while the companion article is unpublished.

    GitHub's "Cite this repository" shows ``preferred-citation`` instead of the
    software, so an in-preparation article would displace the release with its
    DOI. Re-add it (with journal, year and DOI) once the article is accepted,
    and relax this test in the same change.
    """
    assert "preferred-citation" not in _citation(), (
        "CITATION.cff has a preferred-citation; re-add it only once the article is accepted"
    )


# ---------------------------------------------------------------------------
# .zenodo.json describes the software deposit only
# ---------------------------------------------------------------------------

_MANUSCRIPT_WORD = re.compile(r"\bmanuscript\b", re.IGNORECASE)


def test_zenodo_json_describes_software_only() -> None:
    """This public archival-deposit metadata must not reference a manuscript."""
    raw = _ZENODO.read_text()
    assert not _MANUSCRIPT_WORD.search(raw), ".zenodo.json must not contain the word 'manuscript'"
