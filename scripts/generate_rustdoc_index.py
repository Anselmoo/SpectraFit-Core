#!/usr/bin/env python3
"""Write a redirect at the rustdoc root so `/rust-api/` does not 404.

`cargo doc --workspace --no-deps` never writes a root `target/doc/index.html`
for a multi-crate workspace (rustdoc only generates one when a single bin/lib
target makes the "default" page unambiguous), so `/rust-api/` itself 404s on
both GitHub and GitLab Pages even though every per-crate page
(`/rust-api/<crate>/index.html`) renders fine.

This used to fill that gap with a bespoke crate-listing page: ~60 lines of
inline CSS re-implementing a card list, its own font stack, its own light/dark
handling — a second, unthemed mini-site sitting outside the docs, with no
search, no navigation, no theme toggle, and no way to reach the rest of the
documentation except one "Back to docs" link. It duplicated, badly, a job the
docs site already does well.

The crate listing now lives where it belongs: `docs/reference/rust/overview.md`
carries a card grid linking into each crate's rustdoc, inside the real theme,
in the nav, and covered by search. All that is left here is the redirect that
keeps `/rust-api/` from 404ing, pointing at that page.

The redirect is deliberately *relative* (`../reference/rust/overview/`). GitLab
Pages serves this project from its own domain root, but GitHub Pages serves it
as a project page under `/SpectraFit-Core/`, so a root-absolute target would
404 on GitHub — the same trap documented in zensical.toml's `repo_url` comment
and enforced for docs links by tests/audit/test_audit_built_site_links.py.

Run once per `cargo doc` invocation, from both
`.github/workflows/docs-pages.yml` and `.gitlab/65-docs.yml`.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path

# `0; url=` rather than a bare `refresh`: a 0-second meta refresh is what every
# static host supports without server config, and the <link rel=canonical> plus
# the visible fallback link keep it correct for crawlers and for anyone whose
# browser blocks the refresh.
REDIRECT_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>spectrafit-core — Rust API reference</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="0; url={target}">
<link rel="canonical" href="{target}">
</head>
<body>
<p>Redirecting to the <a href="{target}">Rust crate reference</a>.</p>
</body>
</html>
"""

# Relative to /rust-api/index.html, this is the docs page carrying the crate
# card grid. Keep in step with the page's location in `nav` (zensical.toml).
#
# The #anchor matters. The card grid deliberately sits near the END of that
# page, after the responsibility table and the dependency graph — an overview
# page should orient you before it hands you eleven links, and eleven cards at
# the top would push the actual overview below the fold. But someone arriving
# from a bare `/rust-api/` link wants the crate list, not an orientation. The
# anchor serves both: the page reads in a sensible order, and the redirect
# lands on the cards. If the heading text changes, this anchor must change with
# it (toc slugifies "## Generated API docs, per crate" to this slug).
REDIRECT_TARGET = "../reference/rust/overview/#generated-api-docs-per-crate"


def discover_crates(crates_root: Path) -> list[str]:
    """Return workspace crate names, sorted.

    Only used to verify that rustdoc actually emitted something before we plant
    a redirect. Writing a redirect over an empty or failed `cargo doc` would
    turn a loud 404 into a link that quietly lands on a page advertising crate
    docs that are not there.
    """
    names = []
    for manifest in sorted(crates_root.glob("*/Cargo.toml")):
        package = tomllib.loads(manifest.read_text()).get("package", {})
        if name := package.get("name"):
            names.append(name)
    return sorted(names)


def built_modules(crates: list[str], doc_dir: Path) -> list[str]:
    """Return the crates whose rustdoc output actually exists in *doc_dir*."""
    built = []
    for name in crates:
        module = name.replace("-", "_")
        if (doc_dir / module / "index.html").exists():
            built.append(module)
        else:
            print(
                f"warning: {name} -- {module}/index.html not found in {doc_dir}",
                file=sys.stderr,
            )
    return built


def main() -> None:
    """Verify rustdoc output exists, then write the redirect at its root."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, default=Path())
    parser.add_argument("--doc-dir", type=Path, default=Path("target/doc"))
    args = parser.parse_args()

    crates = discover_crates(args.workspace_root / "crates")
    if not crates:
        msg = f"no crates found under {args.workspace_root / 'crates'}"
        raise SystemExit(msg)

    built = built_modules(crates, args.doc_dir)
    if not built:
        msg = (
            f"no crate index.html files found under {args.doc_dir} — "
            "cargo doc likely failed upstream; refusing to write a redirect "
            "that would point at a crate listing with nothing behind it"
        )
        raise SystemExit(msg)

    out_path = args.doc_dir / "index.html"
    out_path.write_text(REDIRECT_TEMPLATE.format(target=REDIRECT_TARGET))
    print(
        f"Wrote {out_path} -> {REDIRECT_TARGET} ({len(built)}/{len(crates)} crates documented)",
    )


if __name__ == "__main__":
    main()
