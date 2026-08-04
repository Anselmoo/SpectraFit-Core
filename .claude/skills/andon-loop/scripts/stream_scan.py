#!/usr/bin/env python3
"""
stream_scan.py — propose a value stream for the andon-loop skill.

Walks a project tree, finds package manifests, counts source files per language,
and infers an ordered chain of stages and the wires between them. Output is a
*proposal* to confirm with the user, never ground truth.

Usage:
    python stream_scan.py [PROJECT_ROOT]   # defaults to cwd

Pure standard library; runs on any Python 3.8+.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

IGNORE = {".git", "node_modules", "target", "dist", "build", ".venv", "venv",
          "__pycache__", ".mypy_cache", ".pytest_cache", ".tox", "site-packages"}

SRC_EXT = {
    "rs": "Rust", "py": "Python", "ts": "TS", "tsx": "TS/React",
    "js": "JS", "jsx": "JS/React", "go": "Go", "java": "Java",
    "cs": "C#", "rb": "Ruby",
}

MANIFESTS = {
    "Cargo.toml": "rust", "pyproject.toml": "python", "setup.py": "python",
    "package.json": "node", "go.mod": "go",
}


def walk(root: Path):
    """Yield files, skipping ignored directories."""
    for p in root.rglob("*"):
        if any(part in IGNORE for part in p.parts):
            continue
        if p.is_file():
            yield p


def read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def detect_stages(root: Path, files: list[Path]) -> list[dict]:
    """One stage per manifest, plus script dirs that emit/consume data."""
    stages: list[dict] = []
    for f in files:
        if f.name in MANIFESTS:
            kind = MANIFESTS[f.name]
            text = read(f)
            stage = {
                "name": f.parent.name or root.name,
                "lang": kind,
                "dir": str(f.parent.relative_to(root)) or ".",
                "manifest": f.name,
                "signals": [],
            }
            low = text.lower()
            if f.name in ("pyproject.toml", "setup.py") and \
                    any(k in low for k in ("maturin", "pyo3", "setuptools-rust", "setuptools_rust")):
                stage["signals"].append("rust-extension")
            if f.name == "Cargo.toml" and "cdylib" in low:
                stage["signals"].append("cdylib")  # feeds an FFI consumer
            if f.name == "package.json" and \
                    any(k in low for k in ('"vite"', '"react"', '"next"', '"@vitejs')):
                stage["signals"].append("web")
            stages.append(stage)
    # Dedup by dir, keep the richest manifest.
    seen: dict[str, dict] = {}
    for s in stages:
        seen.setdefault(s["dir"], s)
    return list(seen.values())


def count_languages(files: list[Path]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in files:
        ext = f.suffix.lstrip(".").lower()
        if ext in SRC_EXT:
            counts[SRC_EXT[ext]] = counts.get(SRC_EXT[ext], 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


def detect_wires(root: Path, stages: list[dict], files: list[Path]) -> list[dict]:
    wires: list[dict] = []
    names = {s["name"] for s in stages}
    by_name = {s["name"]: s for s in stages}

    # Rust -> Python via build coupling.
    for s in stages:
        if s["lang"] == "python" and "rust-extension" in s["signals"]:
            rust = next((r for r in stages if r["lang"] == "rust"), None)
            if rust:
                wires.append(_wire(rust["name"], s["name"], "fast", "ABI / pyo3"))

    # Python -> Python via imports.
    py_files = [f for f in files if f.suffix == ".py"]
    for f in py_files:
        text = read(f)
        importer = _owning_stage(root, f, stages)
        if not importer:
            continue
        for other in names:
            if other == importer:
                continue
            if re.search(rf"\b(import|from)\s+{re.escape(other)}\b", text):
                w = _wire(other, importer, "fast", "import API")
                if w not in wires:
                    wires.append(w)

    # Producer -> JSON: any stage whose code writes json.
    emits_json = set()
    for f in py_files:
        if re.search(r"json\.dump", read(f)):
            owner = _owning_stage(root, f, stages)
            if owner:
                emits_json.add(owner)
    for owner in emits_json:
        wires.append(_wire(owner, "json", "fast", "JSON schema"))

    # JSON / server -> web (fetch).
    web = next((s for s in stages if "web" in s["signals"]), None)
    if web:
        fetches = any(
            re.search(r"fetch\(|axios|\.json\(\)", read(f))
            for f in files if f.suffix in (".ts", ".tsx", ".js", ".jsx")
        )
        if fetches:
            src = "json" if emits_json else (next(iter(emits_json), None) or "server")
            wires.append(_wire(src, web["name"], "fast", "fetch / response shape"))
        # Rendered surface is always a slow-lane wire.
        wires.append(_wire(web["name"], "render", "slow", "Playwright / visual"))

    # Dedup preserving order.
    out: list[dict] = []
    for w in wires:
        if w not in out:
            out.append(w)
    return out


def _owning_stage(root: Path, f: Path, stages: list[dict]) -> str | None:
    rel = str(f.relative_to(root))
    best = None
    for s in stages:
        d = s["dir"]
        prefix = "" if d == "." else d + "/"
        if rel.startswith(prefix) and (best is None or len(prefix) > len(best[1])):
            best = (s["name"], prefix)
    return best[0] if best else None


def _wire(frm: str, to: str, lane: str, contract: str) -> dict:
    return {"from": frm, "to": to, "lane": lane, "contract": contract,
            "status": "unknown"}


def order_along_wires(stages: list[dict], wires: list[dict]) -> list[str]:
    """Order stage names by first appearance walking the wire chain."""
    order: list[str] = []
    for w in wires:
        for n in (w["from"], w["to"]):
            if n not in order:
                order.append(n)
    for s in stages:  # append any stage not on a wire
        if s["name"] not in order:
            order.append(s["name"])
    return order


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 1

    files = list(walk(root))
    stages = detect_stages(root, files)
    langs = count_languages(files)
    wires = detect_wires(root, stages, files)
    ordered_names = order_along_wires(stages, wires)
    stages.sort(key=lambda s: ordered_names.index(s["name"])
                if s["name"] in ordered_names else 999)

    print(f"# Value-stream proposal for: {root.name}\n")
    print(f"Languages detected ({len(langs)}): " +
          ", ".join(f"{k} ({v})" for k, v in langs.items()) or "none")
    print(f"\nStages ({len(stages)}):")
    for s in stages:
        sig = f"  [{', '.join(s['signals'])}]" if s["signals"] else ""
        print(f"  - {s['name']}  ({s['lang']}, {s['dir']}/{s['manifest']}){sig}")

    print(f"\nProposed wires ({len(wires)}):")
    for w in wires:
        lane = "SLOW/visible" if w["lane"] == "slow" else "fast"
        print(f"  {w['from']} --{w['contract']}--> {w['to']}   [{lane}]")

    print("\n--- seed for .andon/ledger.json (confirm before use) ---")
    ledger = {
        "version": 2, "cycle": 1, "pass": 1,
        "cursor": {"stage": ordered_names[0] if ordered_names else None, "pass": 1},
        "mode": "propose", "intent": "harden",
        "acceleration": {"subagents": "required", "mcp": "required"},
        "stages": ordered_names,
        "wires": wires, "constraint": None, "gaps": [], "mcp_candidates": [],
        "history": [],
    }
    print(json.dumps(ledger, indent=2))
    print("\nNOTE: this is a heuristic proposal. Confirm or correct the stream "
          "with the user before writing the ledger. A declared stream wins.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
