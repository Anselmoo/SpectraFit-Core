"""Doc-drift guard: the catalog markdown must stay in sync with the live registries.

``MODELS_CATALOG.md`` carries a human-readable
"Current implementation snapshot" of which kernels / optimization landscapes ship. That
prose has historically gone stale — claiming "16 kernels / 12 landscapes" and marking
already-shipped shapes as not-done — while ``MODEL_REGISTRY`` / ``LANDSCAPE_REGISTRY``
grew underneath it.

These tests are the guard that would have caught that staleness:

* every ``MODEL_REGISTRY`` key is named somewhere in the catalog,
* every ``LANDSCAPE_REGISTRY`` key is named somewhere in the catalog,
* the snapshot count lines equal ``len(MODEL_REGISTRY)`` / ``len(LANDSCAPE_REGISTRY)``.

Parsing is by substring / regex (not exact table layout) so ordinary edits to the
markdown (reordering rows, rewording notes) do not break the guard — only a genuine
drift between the documented set/count and the code does.
"""

from __future__ import annotations

import re
from pathlib import Path

from oracles.models import LANDSCAPE_REGISTRY, MODEL_REGISTRY

_CATALOG = (
    Path(__file__).resolve().parents[2]
    / "python"
    / "oracles"
    / "MODELS_CATALOG.md"
)


def _catalog_text() -> str:
    assert _CATALOG.exists(), f"catalog doc missing: {_CATALOG}"
    return _CATALOG.read_text(encoding="utf-8")


def _named_tokens(text: str) -> set[str]:
    """All snake_case identifiers mentioned anywhere in the catalog markdown."""
    return set(re.findall(r"[A-Za-z][A-Za-z0-9_]*", text))


def test_every_model_registry_key_is_named_in_catalog() -> None:
    """Each registered kernel key must appear (named) in the catalog doc."""
    tokens = _named_tokens(_catalog_text())
    missing = sorted(k for k in MODEL_REGISTRY if k not in tokens)
    assert not missing, (
        f"MODELS_CATALOG.md does not name these MODEL_REGISTRY kernels: {missing}. "
        "Add them (mark ✅) and update the snapshot count."
    )


def test_every_landscape_registry_key_is_named_in_catalog() -> None:
    """Each registered optimization-landscape key must appear in the catalog doc."""
    tokens = _named_tokens(_catalog_text())
    missing = sorted(k for k in LANDSCAPE_REGISTRY if k not in tokens)
    assert not missing, (
        f"MODELS_CATALOG.md does not name these LANDSCAPE_REGISTRY landscapes: {missing}. "
        "Add them (mark ✅) and update the snapshot count."
    )


def test_snapshot_kernel_count_matches_registry() -> None:
    """The '<N> peak/background kernels' snapshot line must equal len(MODEL_REGISTRY)."""
    text = _catalog_text()
    m = re.search(r"\*\*(\d+)\s+peak/background kernels", text)
    assert m, "could not find the '**<N> peak/background kernels**' snapshot line"
    documented = int(m.group(1))
    assert documented == len(MODEL_REGISTRY), (
        f"snapshot says {documented} kernels but MODEL_REGISTRY has {len(MODEL_REGISTRY)}; "
        "update the 'Current implementation snapshot' count in MODELS_CATALOG.md"
    )


def test_snapshot_landscape_count_matches_registry() -> None:
    """The '<N> optimization landscapes' snapshot line must equal len(LANDSCAPE_REGISTRY)."""
    text = _catalog_text()
    m = re.search(r"\*\*(\d+)\s+optimization landscapes", text)
    assert m, "could not find the '**<N> optimization landscapes**' snapshot line"
    documented = int(m.group(1))
    assert documented == len(LANDSCAPE_REGISTRY), (
        f"snapshot says {documented} landscapes but LANDSCAPE_REGISTRY has "
        f"{len(LANDSCAPE_REGISTRY)}; update the snapshot count in MODELS_CATALOG.md"
    )
