"""Structure wires — the *self-description* trust ledger (S-wires).

The W1..W11 wires in :mod:`oracles.audit.wires` verify that the **numbers** this
project reports are true (r², χ²_red, pulls, NIST agreement). They are the reason
the dashboard can put a credibility rung on the science.

But every confirmed audit finding in the 2026-06-26 sweep was a different species
of the *same* defect class, and **none** of them is numerical:

    F6   a hook's "source of truth" comment points at render_report.tsx — a file
         that does not exist anywhere under web/, so the guard is dead code.
    F11  four pre-merge-*.sh hooks are declared as INDEX.yaml stream anchors but
         are wired to NO trigger (0 refs in settings.json / CI / poe).
    ARCH-05 / F13  CLAUDE.md names oracles/contract.py as "the frozen BenchReport
         contract"; the real BenchReport lives in benchmark/contract.py:917.
    ARCH-03  _core.pyi omits model_type_wire_strings, a real runtime PyO3 symbol.
    ARCH-02  PeakModel.spectrafit_type is a bare str resolved by getattr at fit
         time — a THIRD hand-maintained model list with no compile/import binding.

These are all the same bug: **a claim the repository makes about its own structure
that has silently drifted from the structure.** The project rigorously verifies its
output and never verifies its self-description. So a contributor (human or Claude)
reads a comment, an anchor, a doc, a stub — and is led somewhere that no longer
exists.

This module closes that gap with the project's own idiom. Each S-wire returns a
:class:`~oracles.trust_ledger.WireResult` (same record the numerical wires emit),
so structural truth and numerical truth land in **one** ``TrustBlock`` and surface
on the same credibility rung. A drifted comment, a dead anchor, a stale doc, a
phantom stub symbol, or a fourth un-bound model list now *fails a wire* — the same
way a wrong r² does.

Wire-ids are the ``S`` series so they never collide with W1..W11:

    S1  hook-reference liveness   — every path a hook calls a "source of truth"
                                    actually exists on the tree (kills F6).
    S2  anchor-trigger liveness   — every INDEX.yaml stream anchor that *looks*
                                    like an enforced hook is reachable from a real
                                    trigger (settings.json / CI / poe) (kills F11).
    S3  doc-owner truth           — when a doc says "X is the frozen BenchReport
                                    contract", class BenchReport is actually
                                    defined in X (kills ARCH-05 / F13 mislabel).
    S4  FFI-stub completeness     — _core.pyi's top-level defs == the runtime
                                    PyO3 capability set (kills ARCH-03 drift).
    S5  model-list parity         — Rust ModelTypeStr::ALL == Python ModelType
                                    members == every PeakModel.spectrafit_type
                                    registration, all three the same set, so the
                                    "third hand-maintained list" (ARCH-02) can no
                                    longer drift silently.

Each wire is pure (filesystem read only), returns ``skipped`` rather than inflating
a ``pass`` when its inputs are absent, and never raises — a structural verifier that
crashes is just another broken claim.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import TYPE_CHECKING

from oracles.trust_ledger import WireResult

if TYPE_CHECKING:
    from collections.abc import Iterable


def _repo_root(start: Path | None = None) -> Path:
    """Walk up from *start* (default: this file) to the dir holding CLAUDE.md."""
    here = (start or Path(__file__)).resolve()
    for parent in (here, *here.parents):
        if (parent / "CLAUDE.md").is_file():
            return parent
    # Fallback: python/oracles/audit/structure_wires.py -> repo root is parents[3].
    return here.parents[3]


def _ok(wire_id: str, name: str, evidence: str, **details: object) -> WireResult:
    return WireResult(
        wire_id=wire_id,
        name=name,
        status="pass",
        evidence=evidence,
        details=_coerce(details),
    )


def _bad(wire_id: str, name: str, evidence: str, **details: object) -> WireResult:
    return WireResult(
        wire_id=wire_id,
        name=name,
        status="fail",
        evidence=evidence,
        details=_coerce(details),
    )


def _skip(wire_id: str, name: str, evidence: str, **details: object) -> WireResult:
    return WireResult(
        wire_id=wire_id,
        name=name,
        status="skipped",
        evidence=evidence,
        details=_coerce(details),
    )


def _coerce(d: dict[str, object]) -> dict[str, float | int | str | bool | None]:
    out: dict[str, float | int | str | bool | None] = {}
    for k, v in d.items():
        out[k] = v if isinstance(v, (float, int, str, bool)) or v is None else str(v)
    return out


# --------------------------------------------------------------------------- S1
# Hook "source of truth" reference liveness. A hook whose REQUIRED_* comment /
# guard names a file that does not exist is dead code lying about its own scope.

# Path-shaped tokens a hook cites as authority. Matches frontend/render_report.tsx,
# web/src/panels/registry.tsx, python/oracles/contract.py, etc.
# No leading \b: a leading "." (e.g. ".claude/settings.json") is a non-word char,
# so \b would anchor on the first *word* char and silently drop the dot, turning a
# real path into a phantom "claude/settings.json". An optional leading "." captures
# dotfiles/dot-dirs whole.
_PATH_TOKEN = re.compile(
    r"(?<![\w/.-])(\.?(?:[\w.-]+/)+[\w.-]+\.(?:tsx?|py|json|yaml|rs|sh))\b"
)
# Tokens that are obviously not repo paths (urls, globs, std headers) or are
# runtime-generated artifacts that legitimately do not exist at rest (a benchmark
# baseline the hook itself writes/reads, not a source-of-truth that must pre-exist).
_PATH_IGNORE = re.compile(
    r"https?://|node_modules|target/|\*\*|\.git/|results(_index)?\.json"
)
# Lines that cite a path illustratively, not as a source-of-truth claim: a
# shellcheck source= directive (the real source is the adjacent live `source`
# line, resolved relative to the hook dir) and example/usage blocks.
_ILLUSTRATIVE = re.compile(r"shellcheck\s+source=|(?i:\b(?:usage|examples?|e\.g\.)\b)")


def s1_hook_reference_liveness(root: Path | None = None) -> WireResult:
    """S1: every source-of-truth path a hook cites must exist on the tree."""
    root = root or _repo_root()
    hooks_dir = root / ".claude" / "hooks"
    if not hooks_dir.is_dir():
        return _skip("S1", "hook-reference-liveness", "no .claude/hooks dir")
    dangling: list[str] = []
    scanned = 0
    for hook in sorted(hooks_dir.glob("*.sh")):
        scanned += 1
        text = hook.read_text(encoding="utf-8", errors="replace")
        in_example_block = False
        for line in text.splitlines():
            # Track Usage:/Examples: comment blocks: their indented continuation
            # lines cite paths as illustrative CLI args, not source-of-truth claims.
            stripped = line.strip()
            if in_example_block and (not stripped or not stripped.startswith("#")):
                in_example_block = False
            if re.search(r"(?i)\b(?:usage|examples?)\s*:", line):
                in_example_block = True
                continue
            if in_example_block or _ILLUSTRATIVE.search(line):
                continue
            # Only inspect comment lines and guard literals — that is where a
            # "source of truth" path is cited, not in live command substitution.
            if "#" not in line and "render_report" not in line and "==" not in line:
                continue
            for m in _PATH_TOKEN.finditer(line):
                tok = m.group(1)
                if _PATH_IGNORE.search(tok):
                    continue
                # A cited path is live if it resolves from the repo root OR from
                # the hook's own directory ($SCRIPT_DIR-relative sources, e.g.
                # lib/git-hygiene.sh sitting in .claude/hooks/lib/).
                if not (root / tok).exists() and not (hook.parent / tok).exists():
                    dangling.append(f"{hook.name}: {tok}")
    if dangling:
        return _bad(
            "S1",
            "hook-reference-liveness",
            f"{len(dangling)} hook(s) cite a source-of-truth path that does not "
            f"exist: {dangling[:5]}",
            scanned=scanned,
            dangling=len(dangling),
        )
    return _ok(
        "S1",
        "hook-reference-liveness",
        f"all source-of-truth paths cited in {scanned} hooks exist on the tree",
        scanned=scanned,
    )


# --------------------------------------------------------------------------- S2
# Anchor-trigger liveness. INDEX.yaml advertises stream anchors. An anchor that is
# a *.sh hook implies enforcement — so it must be reachable from a real trigger.

_ANCHOR_HOOK = re.compile(r"\b([\w-]+\.sh)\b")


def s2_anchor_trigger_liveness(root: Path | None = None) -> WireResult:
    """S2: every INDEX.yaml *.sh anchor must be reachable from a real trigger."""
    root = root or _repo_root()
    index = root / ".claude" / "skills" / "INDEX.yaml"
    if not index.is_file():
        return _skip("S2", "anchor-trigger-liveness", "no INDEX.yaml")
    hooks_dir = root / ".claude" / "hooks"
    # Only DEPLOYED hooks (the .sh exists on disk) count as advertised enforcement.
    # A name that appears only in a planning comment (e.g. the `to_hooks:` relocation
    # list) with no file yet is a TODO, not a false promise of automation.
    anchors = {
        m.group(1)
        for m in _ANCHOR_HOOK.finditer(index.read_text("utf-8"))
        if (hooks_dir / m.group(1)).is_file()
    }
    if not anchors:
        return _skip(
            "S2", "anchor-trigger-liveness", "no deployed *.sh anchors in INDEX.yaml"
        )

    trigger_blobs: list[str] = []
    for rel in (".claude/settings.json", ".claude/settings.local.json"):
        p = root / rel
        if p.is_file():
            trigger_blobs.append(p.read_text("utf-8", errors="replace"))
    for ci_glob in (".gitlab", ".gitlab-ci.yml", ".github", "pyproject.toml"):
        p = root / ci_glob
        if p.is_file():
            trigger_blobs.append(p.read_text("utf-8", errors="replace"))
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.is_file() and f.suffix in {".yml", ".yaml", ".toml", ".md"}:
                    trigger_blobs.append(f.read_text("utf-8", errors="replace"))
    haystack = "\n".join(trigger_blobs)

    def is_live(anchor: str) -> bool:
        # An anchor is honest if it is EITHER reachable from a real trigger
        # (settings/CI/poe) OR the hook self-declares MANUAL-ONLY — an explicit
        # statement that it is invoked by hand, not silently un-wired. This is the
        # F11 contract: no anchor may imply automation it does not have.
        if anchor in haystack:
            return True
        text = (hooks_dir / anchor).read_text("utf-8", errors="replace")
        return "MANUAL-ONLY" in text

    unwired = sorted(a for a in anchors if not is_live(a))
    if unwired:
        return _bad(
            "S2",
            "anchor-trigger-liveness",
            f"{len(unwired)} INDEX.yaml hook-anchor(s) neither have a trigger in "
            f"settings/CI/poe nor self-declare MANUAL-ONLY (enforcement that is "
            f"advertised but silently never runs): {unwired}",
            anchors=len(anchors),
            unwired=len(unwired),
        )
    return _ok(
        "S2",
        "anchor-trigger-liveness",
        f"all {len(anchors)} hook-anchors reachable from a real trigger",
        anchors=len(anchors),
    )


# --------------------------------------------------------------------------- S3
# Doc-owner truth. When CLAUDE.md says "X is the frozen BenchReport contract",
# `class BenchReport` must actually live in X.

# Captures: a path token on the same line as the phrase "frozen BenchReport
# contract" in either order — CLAUDE.md:231 reads
#   `python/oracles/contract.py` (the frozen `BenchReport` contract)
# i.e. the path PRECEDES "frozen ... BenchReport contract".
_OWNER_CLAIM = re.compile(
    r"`?((?:[\w.-]+/)*[\w.-]+\.py)`?[^\n]{0,80}?frozen[^\n]{0,40}?"
    r"`?BenchReport`?\s+contract",
    re.IGNORECASE,
)


def s3_doc_owner_truth(
    root: Path | None = None,
    *,
    symbol: str = "BenchReport",
    docs: Iterable[str] = ("CLAUDE.md",),
) -> WireResult:
    """S3: a doc that names the *symbol* owner must point where it is defined."""
    root = root or _repo_root()
    defn = re.compile(rf"^\s*class {re.escape(symbol)}\b", re.MULTILINE)
    mislabels: list[str] = []
    claims = 0
    for doc_rel in docs:
        doc = root / doc_rel
        if not doc.is_file():
            continue
        # Collapse whitespace (incl. newlines) so a claim that wraps across lines
        # in the markdown still matches — the bounded [^\n] windows in _OWNER_CLAIM
        # otherwise cannot span the line break between "...frozen" and "BenchReport".
        doc_text = re.sub(r"\s+", " ", doc.read_text("utf-8", errors="replace"))
        for m in _OWNER_CLAIM.finditer(doc_text):
            claims += 1
            claimed_rel = m.group(1)
            target = root / claimed_rel
            if not target.is_file() or not defn.search(
                target.read_text("utf-8", errors="replace")
            ):
                mislabels.append(f"{doc_rel} -> {claimed_rel}")
    if claims == 0:
        return _skip("S3", "doc-owner-truth", f"no '{symbol} contract' claim found")
    if mislabels:
        return _bad(
            "S3",
            "doc-owner-truth",
            f"{len(mislabels)} doc claim(s) name a module as the {symbol} owner "
            f"where `class {symbol}` is not defined: {mislabels}",
            claims=claims,
            mislabels=len(mislabels),
        )
    return _ok(
        "S3",
        "doc-owner-truth",
        f"every doc claim about the {symbol} owner resolves to its real definition",
        claims=claims,
    )


# --------------------------------------------------------------------------- S4
# FFI-stub completeness. The hand-kept _core.pyi must enumerate exactly the
# runtime PyO3 capability set; a missing symbol (model_type_wire_strings) blinds
# the type checker to the canonical model enumerator.


def _pyi_toplevel_defs(pyi: Path) -> set[str]:
    tree = ast.parse(pyi.read_text("utf-8", errors="replace"))
    return {
        n.name
        for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def s4_ffi_stub_completeness(root: Path | None = None) -> WireResult:
    """S4: _core.pyi's top-level defs must equal the runtime PyO3 surface."""
    root = root or _repo_root()
    pyi = root / "python" / "spectrafit_core" / "_core.pyi"
    if not pyi.is_file():
        return _skip("S4", "ffi-stub-completeness", "no _core.pyi")
    declared = _pyi_toplevel_defs(pyi)

    # Source of truth for the runtime surface: the wrap_pyfunction! registrations
    # in the PyO3 module init. We read the .rs rather than importing the compiled
    # extension so the wire runs with no build step.
    lib_rs = root / "crates" / "spectrafit-core" / "src" / "lib.rs"
    if not lib_rs.is_file():
        return _skip("S4", "ffi-stub-completeness", "no spectrafit-core/src/lib.rs")
    runtime = set(
        re.findall(r"wrap_pyfunction!\(\s*([A-Za-z_]\w*)", lib_rs.read_text("utf-8"))
    )
    if not runtime:
        return _skip("S4", "ffi-stub-completeness", "no wrap_pyfunction! registrations")

    missing = sorted(runtime - declared)
    extra = sorted(declared - runtime)
    if missing or extra:
        return _bad(
            "S4",
            "ffi-stub-completeness",
            f"_core.pyi drifted from the runtime PyO3 surface — "
            f"missing {missing}, phantom {extra}",
            runtime=len(runtime),
            declared=len(declared),
            missing=len(missing),
            phantom=len(extra),
        )
    return _ok(
        "S4",
        "ffi-stub-completeness",
        f"_core.pyi declares exactly the {len(runtime)} runtime PyO3 functions",
        runtime=len(runtime),
    )


# --------------------------------------------------------------------------- S5
# Model-list parity. Rust ModelTypeStr::ALL ≡ Python ModelType members ≡ every
# PeakModel.spectrafit_type registration. The third list (spectrafit_type) is the
# one ARCH-02 flags as un-bound; this wire binds all three into one set.


def _rust_modeltype_wire_strings(root: Path) -> set[str]:
    types_rs = root / "crates" / "spectrafit-types" / "src" / "types.rs"
    if not types_rs.is_file():
        return set()
    text = types_rs.read_text("utf-8", errors="replace")
    # The canonical wire list is the `Variant => "wire"` arms inside the
    # model_manifest! { ... } INVOCATION (which generates ModelTypeStr::ALL +
    # as_str()). We must scope to that brace-block so we don't also capture
    # TerminationReason / other `=>` arms elsewhere in the file.
    start = text.find("model_manifest! {")
    if start == -1:
        return set()
    depth = 0
    end = start
    for i in range(text.find("{", start), len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    block = text[start:end]
    return {m.group(1) for m in re.finditer(r'\b[A-Z]\w*\s*=>\s*"([\w]+)"', block)}


def _python_modeltype_members(root: Path) -> dict[str, str]:
    models_py = root / "python" / "spectrafit_core" / "models.py"
    if not models_py.is_file():
        return {}
    out: dict[str, str] = {}
    for m in re.finditer(
        r'^\s*([A-Z][A-Z0-9_]*)\s*=\s*["\']([\w]+)["\']',
        models_py.read_text("utf-8", errors="replace"),
        re.MULTILINE,
    ):
        out[m.group(1)] = m.group(2)  # member NAME -> wire VALUE
    return out


def _registered_spectrafit_types(root: Path) -> set[str]:
    reg = root / "python" / "oracles" / "models.py"
    if not reg.is_file():
        return set()
    return set(
        re.findall(
            r'spectrafit_type\s*=\s*["\']([A-Z][A-Z0-9_]*)["\']',
            reg.read_text("utf-8", errors="replace"),
        )
    )


def s5_model_list_parity(root: Path | None = None) -> WireResult:
    """S5: Rust ModelTypeStr ≡ Python ModelType ≡ every spectrafit_type name."""
    root = root or _repo_root()
    rust_values = _rust_modeltype_wire_strings(root)
    py_members = _python_modeltype_members(root)  # NAME -> VALUE
    registered = _registered_spectrafit_types(root)  # NAMEs used at registration

    if not rust_values or not py_members:
        return _skip(
            "S5",
            "model-list-parity",
            "could not read Rust ModelTypeStr or Python ModelType",
        )

    py_values = set(py_members.values())
    py_names = set(py_members)

    problems: list[str] = []
    # 1. Rust wire VALUE set must equal Python ModelType VALUE set.
    only_rust = rust_values - py_values
    only_py = py_values - rust_values
    if only_rust:
        problems.append(
            f"in Rust ModelTypeStr but not Python ModelType: {sorted(only_rust)}"
        )
    if only_py:
        problems.append(
            f"in Python ModelType but not Rust ModelTypeStr: {sorted(only_py)}"
        )
    # 2. Every spectrafit_type=... NAME used at registration must be a real
    #    ModelType member NAME (ARCH-02: getattr(ModelType, name) must resolve).
    unbound = registered - py_names
    if unbound:
        problems.append(
            f"PeakModel.spectrafit_type names with no ModelType member "
            f"(getattr would AttributeError at fit time): {sorted(unbound)}"
        )

    if problems:
        return _bad(
            "S5",
            "model-list-parity",
            "the three hand-maintained model lists disagree: " + " | ".join(problems),
            rust=len(rust_values),
            python=len(py_values),
            registered=len(registered),
        )
    return _ok(
        "S5",
        "model-list-parity",
        f"Rust ({len(rust_values)}) ≡ Python ModelType ≡ all "
        f"{len(registered)} spectrafit_type registrations resolve",
        rust=len(rust_values),
        python=len(py_values),
        registered=len(registered),
    )


# --------------------------------------------------------------------------- run

S_WIRES = (
    s1_hook_reference_liveness,
    s2_anchor_trigger_liveness,
    s3_doc_owner_truth,
    s4_ffi_stub_completeness,
    s5_model_list_parity,
)


def run_structure_wires(root: Path | None = None) -> list[WireResult]:
    """Run every S-wire, never raising — a crashing verifier is a broken claim."""
    root = root or _repo_root()
    results: list[WireResult] = []
    for wire in S_WIRES:
        try:
            results.append(wire(root))
        except Exception as exc:  # noqa: BLE001 — a wire must not take down the audit
            results.append(
                _bad(
                    wire.__name__.split("_")[0].upper(),
                    wire.__name__,
                    f"structure wire raised: {type(exc).__name__}: {exc}",
                )
            )
    return results


def main() -> int:
    """CLI: print each S-wire and exit non-zero on any structural drift."""
    results = run_structure_wires()
    glyph = {"pass": "✓", "fail": "✗", "skipped": "–", "warn": "!", "gap": "○"}
    worst = 0
    for r in results:
        print(f"  {glyph.get(r.status, '?')} {r.wire_id} {r.name}: {r.evidence}")
        if r.status == "fail":
            worst = 1
    verdict = "STRUCTURAL DRIFT" if worst else "self-description is true"
    print(f"\n  structure ledger: {verdict}")
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
