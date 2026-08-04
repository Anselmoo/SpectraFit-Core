#!/usr/bin/env python3
"""Gate the two crate conventions that are otherwise silently regressable.

Both house rules 22 and 26 have the same failure shape: they hold today, nothing
notices when a NEW crate breaks them, and the breakage is invisible rather than
loud. This script is the missing gate.

1. **Rule 22 — `[lints] workspace = true`.** `[workspace.lints.rust]` in the root
   `Cargo.toml` denies `unsafe_code`, but Cargo applies a workspace lint table
   ONLY to crates that opt in with this stanza. A crate added without it is
   silently exempt from the deny — it compiles clean with `unsafe` in it, and no
   existing check would say a word.

2. **Rule 26 — no new `pub mod`.** Nine of eleven crates keep their modules
   private behind a curated `pub use`. `spectrafit-models` and `spectrafit-types`
   are deliberate library-shaped exceptions (see `DECISIONS.md`). A new `pub mod`
   elsewhere defeats rule 21's curated re-export list — the module path still
   resolves, so the list becomes a review aid rather than a boundary — and it
   blinds `dead_code`, since rustc cannot prove a `pub` item unused.

Run standalone, or via the `crate-conventions` pre-commit hook.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CRATES = REPO / "crates"

# Crates permitted to declare `pub mod`, with the reason. Extending this set is a
# design decision that belongs in DECISIONS.md, not a quick edit here.
PUB_MOD_ALLOWED = {
    "spectrafit-models": "library-shaped: catalogue of 30 independently useful kernels",
    "spectrafit-types": "library-shaped: the shared IR every crate imports",
}

LINTS_STANZA = re.compile(r"^\[lints\]\s*\n\s*workspace\s*=\s*true", re.MULTILINE)
PUB_MOD = re.compile(r"^pub mod\s+([A-Za-z0-9_]+)\s*;", re.MULTILINE)


def main() -> int:
    """Check every crate against rules 22 and 26; return 1 on any violation."""
    if not CRATES.is_dir():
        print(f"crate-conventions: no crates/ directory at {CRATES}", file=sys.stderr)
        return 1

    failures: list[str] = []
    checked = 0

    for crate_dir in sorted(p for p in CRATES.iterdir() if p.is_dir()):
        manifest = crate_dir / "Cargo.toml"
        if not manifest.is_file():
            continue
        checked += 1
        name = crate_dir.name

        # --- Rule 22 -------------------------------------------------------
        if not LINTS_STANZA.search(manifest.read_text(encoding="utf-8")):
            failures.append(
                f"{name}/Cargo.toml: missing `[lints]\\nworkspace = true`.\n"
                f"    Without it this crate does NOT inherit "
                f'[workspace.lints.rust] unsafe_code = "deny" — it is silently\n'
                f"    exempt from the workspace safety policy (house rule 22)."
            )

        # --- Rule 26 -------------------------------------------------------
        lib = crate_dir / "src" / "lib.rs"
        if lib.is_file() and name not in PUB_MOD_ALLOWED:
            pub_mods = PUB_MOD.findall(lib.read_text(encoding="utf-8"))
            if pub_mods:
                listed = ", ".join(sorted(pub_mods))
                failures.append(
                    f"{name}/src/lib.rs: declares `pub mod` ({listed}).\n"
                    f"    Pipeline crates keep modules private behind a curated "
                    f"`pub use` (house rule 26).\n"
                    f"    `pub mod` lets consumers bypass that list and blinds "
                    f"dead_code analysis.\n"
                    f"    Genuinely library-shaped? Add it to PUB_MOD_ALLOWED here "
                    f"AND record the decision in DECISIONS.md."
                )

    if failures:
        print("crate-conventions: FAILED\n", file=sys.stderr)
        for f in failures:
            print(f"  - {f}\n", file=sys.stderr)
        return 1

    exempt = ", ".join(sorted(PUB_MOD_ALLOWED))
    print(
        f"crate-conventions: OK — {checked} crates checked (pub mod exempt: {exempt})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
