"""Design-token parity: the dashboard's tokens vs the docs site's tokens.

``web/src/style/tokens.css`` and ``docs/stylesheets/tokens/palette.css`` describe one
design system across two build pipelines that share no build-time plumbing. The docs
file states the contract in its own header — it "mirrors ``web/src/style/tokens.css``
… **without importing that file directly**" — and until now nothing enforced it. The
scan in ``analysis/web-docs/CONSISTENCY_SCAN.md`` found the values still identical, so
this test defends an alignment that currently holds rather than repairing a broken one.

Failure mode it guards: someone edits ``--space-5`` (or a solver colour) on one side.
Both sites still build, both suites still pass, and the drift is visible only to a
human comparing the two rendered sites side by side.

Three separate contracts, because they have genuinely different rules:

1. **Scheme-invariant scalars** (spacing, radius) must be byte-identical. They do not
   vary by light/dark, so there is nothing to reconcile.
2. **Solver identity colours in dark** must match the dashboard's resolved hex exactly.
   This is the shared vocabulary — "spectrafit is blue, jax is pink" — and a swatch
   that disagrees between the two surfaces is precisely the confusion the port fixed.
3. **Solver identity colours in light** must merely *exist* and must NOT equal the dark
   hex. The dashboard is dark-only by design (``tokens.css`` header), so copying its
   hexes onto a white page would be a contrast bug; light values are the Apple
   light-appearance counterparts and are deliberately different.

Not asserted here: WCAG ratios. Those are documented per-token in ``palette.css`` and
belong to a dedicated a11y check, not to a drift guard.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_TOKENS = REPO_ROOT / "web" / "src" / "style" / "tokens.css"
DOCS_TOKENS = REPO_ROOT / "docs" / "stylesheets" / "tokens" / "palette.css"

SOLVER_IDS = (
    "spectrafit",
    "lmfit",
    "jax",
    "scipy-ls-lm",
    "scipy-ls-trf",
    "scipy-ls-dogbox",
)

#: Scheme-invariant scalar tokens that must agree byte-for-byte across both files.
SHARED_SCALARS = (
    "--space-1",
    "--space-2",
    "--space-3",
    "--space-4",
    "--space-5",
    "--space-6",
    "--space-7",
    "--space-8",
    "--space-9",
    "--radius-sm",
    "--radius-md",
    "--radius-lg",
    "--radius-xl",
    "--radius-full",
)


def _strip_comments(css: str) -> str:
    """Drop /* … */ blocks so commented-out or documented values never match.

    Load-bearing: both files carry long rationale comments that quote hex values
    (e.g. "NOT systemOrange #ff9500"), and a naive regex would happily read one of
    those as a declaration.
    """
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def _declarations(css: str) -> dict[str, str]:
    """Map every ``--token: value`` declaration to its value, last one winning."""
    out: dict[str, str] = {}
    for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", _strip_comments(css)):
        out[name] = value.strip()
    return out


def _scheme_block(css: str, scheme: str) -> str:
    """Return the body of a ``[data-md-color-scheme="<scheme>"]`` rule."""
    stripped = _strip_comments(css)
    start = stripped.index(f'[data-md-color-scheme="{scheme}"]')
    brace = stripped.index("{", start)
    depth, i = 0, brace
    while i < len(stripped):
        if stripped[i] == "{":
            depth += 1
        elif stripped[i] == "}":
            depth -= 1
            if depth == 0:
                return stripped[brace + 1 : i]
        i += 1
    raise AssertionError(f"unbalanced braces around {scheme!r} block")


def _resolve(value: str, table: dict[str, str], depth: int = 0) -> str:
    """Resolve a single ``var(--x)`` indirection chain to a literal.

    ``tokens.css`` defines solver colours as aliases (``--c-jax: var(--system-pink)``),
    so comparing raw declarations across the two files would compare an alias to a hex.
    """
    if depth > 8:  # pragma: no cover - only reachable via a cyclic definition
        raise AssertionError(f"var() chain too deep or cyclic at {value!r}")
    match = re.fullmatch(r"var\(\s*(--[\w-]+)\s*\)", value.strip())
    if not match:
        return value.strip().lower()
    target = match.group(1)
    assert target in table, f"{value!r} references undefined token {target!r}"
    return _resolve(table[target], table, depth + 1)


@pytest.fixture(scope="module")
def web() -> dict[str, str]:
    return _declarations(WEB_TOKENS.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def docs_light() -> dict[str, str]:
    css = DOCS_TOKENS.read_text(encoding="utf-8")
    return _declarations(_scheme_block(css, "default"))


@pytest.fixture(scope="module")
def docs_slate() -> dict[str, str]:
    css = DOCS_TOKENS.read_text(encoding="utf-8")
    return _declarations(_scheme_block(css, "slate"))


@pytest.fixture(scope="module")
def docs_root() -> dict[str, str]:
    return _declarations(DOCS_TOKENS.read_text(encoding="utf-8"))


def test_token_files_exist() -> None:
    """Guard the paths themselves — a move would otherwise silently skip every check."""
    assert WEB_TOKENS.is_file(), f"missing {WEB_TOKENS}"
    assert DOCS_TOKENS.is_file(), f"missing {DOCS_TOKENS}"


@pytest.mark.parametrize(
    ("docs_token", "web_token"),
    [("--md-text-font", "--font-body"), ("--md-code-font", "--font-mono")],
)
def test_type_families_match(
    docs_token: str, web_token: str, web: dict[str, str], docs_root: dict[str, str]
) -> None:
    """The docs site and the dashboard resolve to the same first font family.

    Guards a real bug. The docs site self-hosts IBM Plex Sans and JetBrains Mono
    byte-identically to the dashboard's copies, yet rendered ``document.body``,
    the footer nav, the skip link and both tooltip variants in **Inter** — and
    fetched Inter from Google on every page. Cause: ``zensical.toml`` set no
    ``[theme.font]``, so Zensical injected its own ``--md-text-font: "Inter"``,
    and ``typography/type.css`` fought it selector-by-selector instead of
    setting the variable, covering only the surfaces someone enumerated.

    Asserting on the DOCS token (not on a list of selectors) is deliberate: it
    is exactly the level the earlier fix got wrong, so a regression to
    per-selector patching fails here.
    """
    assert web_token in web, f"{web_token} missing from {WEB_TOKENS.name}"
    assert docs_token in docs_root, (
        f"{docs_token} missing from {DOCS_TOKENS.name}. Setting the theme "
        "variable is what stops Zensical's default font from leaking; do not "
        "replace it with per-selector font-family rules."
    )

    def first(stack: str) -> str:
        """First family of a font stack, unquoted and case-folded."""
        return stack.split(",")[0].strip().strip("\"'").lower()

    assert first(docs_root[docs_token]) == first(web[web_token]), (
        f"type family drifted: docs {docs_token}={docs_root[docs_token]!r} vs "
        f"web {web_token}={web[web_token]!r}"
    )


@pytest.mark.parametrize("token", SHARED_SCALARS)
def test_scheme_invariant_scalars_match(
    token: str, web: dict[str, str], docs_root: dict[str, str]
) -> None:
    """Spacing and radius are identical in both files (docs/palette.css's own claim)."""
    assert token in web, f"{token} missing from {WEB_TOKENS.name}"
    assert token in docs_root, f"{token} missing from {DOCS_TOKENS.name}"
    assert web[token] == docs_root[token], (
        f"{token} drifted: web={web[token]!r} docs={docs_root[token]!r}. "
        "These describe one scale across two pipelines; update both or neither."
    )


@pytest.mark.parametrize("solver", SOLVER_IDS)
def test_solver_identity_dark_matches_dashboard(
    solver: str, web: dict[str, str], docs_slate: dict[str, str]
) -> None:
    """The dark solver swatch is the same colour on the docs site and the dashboard.

    This is the shared vocabulary. Both surfaces are dark here, so there is no
    contrast reason to diverge and an exact match is required.
    """
    token = f"--c-{solver}"
    assert token in web, f"{token} missing from {WEB_TOKENS.name}"
    assert token in docs_slate, f"{token} missing from the docs slate block"
    expected = _resolve(web[token], web)
    actual = _resolve(docs_slate[token], docs_slate)
    assert actual == expected, (
        f"{token} disagrees in dark: dashboard={expected} docs={actual}. "
        "A reader crossing between the two surfaces would see the same solver "
        "in two different colours."
    )


@pytest.mark.parametrize("solver", SOLVER_IDS)
def test_solver_identity_light_exists_and_differs(
    solver: str, docs_light: dict[str, str], docs_slate: dict[str, str]
) -> None:
    """Light values exist and are NOT the dark hexes copied onto a white page."""
    token = f"--c-{solver}"
    assert token in docs_light, f"{token} missing from the docs light block"
    light = _resolve(docs_light[token], docs_light)
    dark = _resolve(docs_slate[token], docs_slate)
    assert light != dark, (
        f"{token} uses the dark hex {dark} in the light scheme. The dashboard's "
        "palette is dark-appearance only; its hexes fail contrast on white."
    )


@pytest.mark.parametrize("solver", SOLVER_IDS)
@pytest.mark.parametrize("suffix", ["", "-text"])
def test_solver_token_pair_is_complete(
    solver: str, suffix: str, docs_light: dict[str, str], docs_slate: dict[str, str]
) -> None:
    """Every solver carries identity **and** -text in BOTH schemes.

    A half-populated scheme is the likely shape of a future mistake: someone adds a
    solver to one block and forgets the other, and the missing token silently falls
    back to whatever the cascade provides.

    This asserted a *triplet* until the ``-soft`` tier was removed. That tier was
    added speculatively and never consumed — 6 declarations in ``tokens.css`` and
    12 here, zero ``var()`` references on either side — so asserting it only
    guaranteed that dead weight stayed symmetrical.
    """
    token = f"--c-{solver}{suffix}"
    assert token in docs_light, f"{token} missing from the docs light block"
    assert token in docs_slate, f"{token} missing from the docs slate block"


def test_no_solver_is_missing_from_docs(
    web: dict[str, str], docs_slate: dict[str, str]
) -> None:
    """Adding a solver to the dashboard must not leave the docs site behind."""
    web_solvers = {
        m.group(1)
        for k in web
        if (m := re.fullmatch(r"--c-([\w-]+?)(?:-soft)?", k)) is not None
    }
    docs_solvers = {
        m.group(1)
        for k in docs_slate
        if (m := re.fullmatch(r"--c-([\w-]+?)(?:-soft|-text)?", k)) is not None
    }
    missing = web_solvers - docs_solvers
    assert not missing, (
        f"solver(s) {sorted(missing)} exist in {WEB_TOKENS.name} but not in the docs "
        f"palette. Add --c-<id>, --c-<id>-text and --c-<id>-soft to BOTH scheme blocks."
    )
