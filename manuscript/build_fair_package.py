#!/usr/bin/env python3
"""Assemble the complete reported-run data package the manuscript points at.

The paper cites a benchmark run, a ladder of repetition depths, six figures, and
a set of measurement sidecars. Those live in different places in the repository,
which is fine for development and wrong for a reader: a person following the
paper's data availability statement should get **one** thing, self-describing,
with checksums.

This builds that thing.

Three problems it fixes, all raised on the manuscript draft:

**Run naming.** Runs are labelled ``<date>_run_NNN`` by a counter over the
directories present on whichever machine produced them, so the same label names
different runs on different hosts and is not an identifier at all. The package
is named from content instead: the case-catalog fingerprint, the host, and the
run date. Two packages with the same name describe the same suite measured on
the same machine on the same day; two with different names differ in something
that matters.

**Completeness.** The ladder directory is already a well-formed RO-Crate, but it
is the ladder alone. The figures, the scripts that draw them, the pinned summary
and measurement sidecars they read, and the reference list are all part of what a
reader needs to redo the paper's analysis, and none of them are in it. This
script therefore copies whole directories rather than a hand-kept file list: the
list is what went stale last time, and a list cannot know about an artifact added
after it was written.

**Licence.** The package is not uniformly MIT and must not say it is. Two files
in it are third-party measured data reproduced by permission. They carry their
own licence entity in the RO-Crate; see ``RESTRICTED_FILES`` below.

Usage::

    python3 manuscript/build_fair_package.py                     # build
    python3 manuscript/build_fair_package.py --out DIR           # elsewhere
    python3 manuscript/build_fair_package.py --verify DIR        # re-check

The output is a build product, not a committed duplicate: the inputs are all
under version control already, and committing a second copy would create two
things that can disagree.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LADDER = ROOT / "manuscript/examples/ladder"
DEFAULT_OUT = ROOT / "manuscript/fair-package"

# Whole directories, copied under the destination name given. The destination
# names deliberately mirror `manuscript/examples/`: every figure script resolves
# its inputs relative to its own file, so `fig_ladder_stability.py` reads both
# `../ladder/` and `../seed-sweep/`, `fig_model_graph.py` reads `../fecl4/` and
# `fig_nist_catalogue.py` reads `../nist_unimplemented/`. Renaming a directory in
# the package silently breaks those scripts for the reader, which is the one thing
# the package exists to prevent.
SOURCE_TREES: tuple[tuple[str, str], ...] = (
    ("manuscript/examples/ladder", "ladder"),
    ("manuscript/examples/seed-sweep", "seed-sweep"),
    ("manuscript/examples/figures", "figures"),
    ("manuscript/examples/fecl4", "fecl4"),
    ("manuscript/examples/nist_unimplemented", "nist_unimplemented"),
)
SOURCE_FILES: tuple[tuple[str, str], ...] = (("manuscript/draft/references.ris", "references.ris"),)

# Build detritus that is never an input to anything.
SKIP_DIR_NAMES = frozenset({"__pycache__", ".ipynb_checkpoints", ".pytest_cache"})
SKIP_FILE_NAMES = frozenset({".DS_Store", ".gitkeep"})
# `.log` joins the detritus list: the 50 per-seed `run.log` files are a four-line
# human-readable rendering of numbers the `provenance.json` beside them already
# carries at full precision (`resources`, `headline`), they are caught by
# `.gitignore`'s `*.log` rule, and they are therefore absent from every clean
# clone. Packaging them made the deposit depend on which machine built it: 299
# files on the host that ran the sweep, 249 anywhere else. A deposit that cannot
# be rebuilt is not reusable in the FAIR sense, whatever its checksums say.
SKIP_SUFFIXES = frozenset({".pyc", ".pyo", ".log"})

# Files whose licence is NOT this repository's MIT. Keyed by package-relative
# path; the value names the licence entity minted in the RO-Crate. Everything
# stated here is recorded in the repository — `manuscript/examples/fecl4/README.md`
# and `manuscript/draft/sections/data_availability.md` — and nothing is inferred.
FECL4_LICENCE_ID = "#licence-fecl4-spectra-by-permission"
RESTRICTED_FILES: dict[str, str] = {
    "fecl4/FeCl4_d5.txt": FECL4_LICENCE_ID,
    "fecl4/FeCl4_d6.txt": FECL4_LICENCE_ID,
}
MIT_ID = "https://spdx.org/licenses/MIT.html"
MANIFEST_LICENCE_ID = "#licence-manifest"

FECL4_CITATION = (
    "Wasinger EC, de Groot FMF, Hedman B, Hodgson KO, Solomon EI. "
    "L-edge X-ray absorption spectroscopy of non-heme iron sites: experimental "
    "determination of differential orbital covalency. "
    "J Am Chem Soc. 2003;125(42):12894-906. doi:10.1021/ja034634s"
)
FECL4_LICENCE_TEXT = (
    "Third-party measured data, reproduced and redistributed with the authors' "
    "permission. NOT covered by the MIT licence that covers the rest of this "
    "package: that licence applies to the code. The permission is specific to "
    "this reproduction and redistribution and grants nothing onward -- the "
    "spectrafit-core repository records no reuse licence for these spectra. A "
    "third party wanting to use them should cite Wasinger et al. (2003) and seek "
    "permission from those authors."
)
MANIFEST_LICENCE_TEXT = (
    "This package is not uniformly licensed. Every file is MIT-licensed, as the "
    "spectrafit-core repository is, EXCEPT those files that carry their own "
    "`license` property in this crate. Two do, and they are the only two: "
    + ", ".join(f"`{p}`" for p in sorted(RESTRICTED_FILES))
    + ". Resolve a file's licence from its own `license` property first, and "
    "fall back to MIT only where a file declares none."
)

# `checksums.sha256` is written last and so cannot carry its own digest; the
# RO-Crate lists it as a part without one and says why.
CHECKSUMS_NAME = "checksums.sha256"
CRATE_NAME = "ro-crate-metadata.json"


def sha256(path: Path) -> str:
    """Return the SHA-256 of a file, read in chunks so size is never a hazard."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_json(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, mode="rt", encoding="utf-8") as fh:
        return json.load(fh)


def _skipped(path: Path) -> bool:
    """Return True for build detritus that is never an input to anything."""
    return (
        any(part in SKIP_DIR_NAMES for part in path.parts)
        or path.name in SKIP_FILE_NAMES
        or path.suffix in SKIP_SUFFIXES
    )


def package_name(ladder: dict) -> str:
    """Name the package from its content rather than from a per-host counter."""
    catalog = ladder["config"]["catalog"]["fingerprint_sha256"][:8]
    host = ladder["environment"]["host"]["hostname"]
    date = ladder["generated_utc"][:10]
    return f"spectrafit-core-benchmark_{date}_{host}_{catalog}"


def _untracked(paths: list[Path]) -> set[Path]:
    """Return which of `paths` git does not track, so the build can say so.

    The package's premise is that every input is already under version control.
    That premise is worth checking rather than asserting: an artifact written but
    never committed would otherwise ship inside a package claiming the opposite.
    """
    if not paths:
        return set()
    try:
        proc = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "-z", "--", *[str(p) for p in paths]],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return set()
    tracked = {ROOT / p for p in proc.stdout.split("\0") if p}
    return {p for p in paths if p.resolve() not in tracked}


def collect(target: Path) -> list[Path]:
    """Copy every input into `target`; return the resulting files, sorted."""
    sources: list[Path] = []
    for src_rel, dst_rel in SOURCE_TREES:
        src = ROOT / src_rel
        if not src.is_dir():
            print(f"  note: {src_rel}/ absent, not packaged")
            continue
        for path in sorted(src.rglob("*")):
            if not path.is_file() or _skipped(path.relative_to(src)):
                continue
            dst = target / dst_rel / path.relative_to(src)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dst)
            sources.append(path)
    for src_rel, dst_name in SOURCE_FILES:
        src = ROOT / src_rel
        if not src.is_file():
            print(f"  note: {src_rel} absent, not packaged")
            continue
        shutil.copy2(src, target / dst_name)
        sources.append(src)

    # Enforced, not advisory. This was a warning, and the thing it warned about
    # shipped anyway: 50 untracked `run.log` files sat in the package, in both
    # checksum manifests and in the RO-Crate, through every build. A warning that
    # is printed and stepped over is a warning the build has decided not to mean.
    # The premise in `_untracked` -- every input is under version control -- is
    # the only thing that makes the deposit rebuildable by someone who is not the
    # author, so it is now a build failure.
    loose = _untracked(sources)
    if loose:
        lines = "\n".join(f"    {p.relative_to(ROOT)}" for p in sorted(loose))
        msg = (
            f"{len(loose)} packaged input(s) are not tracked by git:\n{lines}\n"
            "    A clean clone would build a different package, so this one is not\n"
            "    reproducible. Commit them, or add them to the skip lists if they\n"
            "    are build detritus rather than an input."
        )
        detail = f"error: {msg}"
        raise SystemExit(detail)
    return sorted(p for p in target.rglob("*") if p.is_file())


def _file_entity(target: Path, path: Path) -> dict:
    """Describe one packaged file, carrying its own licence where it has one."""
    rel = path.relative_to(target).as_posix()
    entity = {
        "@id": rel,
        "@type": "File",
        "contentSize": path.stat().st_size,
        "sha256": sha256(path),
    }
    licence = RESTRICTED_FILES.get(rel)
    if licence:
        entity["license"] = {"@id": licence}
        entity["citation"] = FECL4_CITATION
    return entity


def crate(target: Path, name: str, files: list[Path]) -> dict:
    """Build the RO-Crate graph: one entity per file, plus the licence manifest.

    `hasPart` enumerates every file in the package except this metadata document,
    which RO-Crate 1.1 models as the crate's descriptor rather than as one of its
    parts. `checksums.sha256` is a part but is written after this document, so it
    is listed without a digest and says so.
    """
    parts = [p.relative_to(target).as_posix() for p in files] + [CHECKSUMS_NAME]
    graph = [
        {
            "@id": CRATE_NAME,
            "@type": "CreativeWork",
            "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
            "about": {"@id": "./"},
        },
        {
            "@id": "./",
            "@type": "Dataset",
            "name": name,
            "description": (
                "Complete data package for the benchmark run reported in the "
                "spectrafit-core software metapaper: the repetition-depth ladder, "
                "the pinned benchmark summary and measurement sidecars, every "
                "figure the repository produces -- including the three the paper "
                "has no room for -- the scripts that draw them, the FeCl4 "
                "case-study data, and the manuscript bibliography."
            ),
            "datePublished": datetime.now(UTC).strftime("%Y-%m-%d"),
            "license": {"@id": MANIFEST_LICENCE_ID},
            "hasPart": [{"@id": rel} for rel in parts],
        },
        {
            "@id": MANIFEST_LICENCE_ID,
            "@type": "CreativeWork",
            "name": "MIT, except where a file declares its own licence",
            "description": MANIFEST_LICENCE_TEXT,
        },
        {
            "@id": MIT_ID,
            "@type": "CreativeWork",
            "name": "MIT License",
            "identifier": "MIT",
        },
        {
            "@id": FECL4_LICENCE_ID,
            "@type": "CreativeWork",
            "name": "Reproduced by permission; no onward reuse licence",
            "description": FECL4_LICENCE_TEXT,
            "citation": FECL4_CITATION,
        },
    ]
    graph += [_file_entity(target, p) for p in files]
    graph.append(
        {
            "@id": CHECKSUMS_NAME,
            "@type": "File",
            "description": (
                "SHA-256 of every other file in this package, including this "
                "crate. Written after this document, so no digest of it appears "
                "here; it is the manifest, not a payload."
            ),
        },
    )
    return {"@context": "https://w3id.org/ro/crate/1.1/context", "@graph": graph}


def readme(name: str, ladder: dict) -> str:
    """Write the package's own front page, headlined by the rung the paper quotes."""
    deepest = ladder["rungs"][-1]
    head = deepest["headline"]
    env = ladder["environment"]
    rows = "\n".join(
        f"| {r['reps_requested']} | {r['reps_effective']} | "
        f"{r['headline']['geomean_speedup_vs_baseline']:.3f} | "
        f"{r['wall_seconds'] / 60:.0f} | {r['exit_status']} |"
        for r in ladder["rungs"]
    )
    restricted = "\n".join(f"- `{p}`" for p in sorted(RESTRICTED_FILES))
    # Re-read the fingerprint from the ladder rather than splitting it back out
    # of the name: the name is derived from it, not the other way round.
    catalog = ladder["config"]["catalog"]["fingerprint_sha256"][:8]
    return f"""# {name}

The complete data package for the benchmark run reported in the spectrafit-core
software metapaper. Everything the paper's figures and tables are derived from is
here, and nothing here is derived from anything absent.

The package is named from its content, not from a run counter. `{catalog}`
is the first eight hex digits of the case catalog's SHA-256 fingerprint, so the
name changes if the suite changes. Labels of the form `<date>_run_NNN` that
appear inside the artifacts are per-machine counters and are not identifiers.

## Licence

**This package is not uniformly MIT, and a blanket claim on it would be false.**

Every file is MIT-licensed, as the spectrafit-core repository is, **except** the
following, which are third-party measured data reproduced and redistributed with
the authors' permission:

{restricted}

{FECL4_LICENCE_TEXT}

> {FECL4_CITATION}

`{CRATE_NAME}` carries this as machine-readable metadata: those two files hold
their own `license` property, and a consumer should resolve any file's licence
from its own `license` first, falling back to MIT only where a file declares
none.

## What the run reports

Headline figures are the deepest rung, which is the one the paper quotes.

| | |
|---|---|
| geometric-mean speedup vs {head["baseline_solver_id"]} | {head["geomean_speedup_vs_baseline"]:.4f} |
| harmonic-mean speedup | {head["harmonic_mean_speedup_vs_baseline"]:.4f} |
| max abs delta r^2 | {head["max_abs_delta_r2"]:.3e} |
| win rate | {head["spectrafit_win_rate"]:.3f} |
| cases | {head["n_cases"]} |
| regressions | {head["regressions"]} |
| backends | {", ".join(head["backends"])} |

Measured on `{env["host"]["hostname"]}` ({env["host"]["cpu"]}, {env["host"]["cores"]} cores,
{env["host"]["ram_gb"]} GB) at commit `{env["git"]["commit"][:7]}`, generated
{ladder["generated_utc"]}.

The full ladder, every rung of which ships:

| `--reps` | effective depth | geomean speedup | wall (min) | exit |
|---:|---:|---:|---:|---:|
{rows}

The two depths are not the same number: the suite phase runs `max(1, reps // 2)`
timed solves. Quote `reps_effective`.

Stopping tolerances are **not** normalised across backends; each runs at its own
library default, recorded per backend in `ladder/ladder.json` under
`config.solvers`. Read `methodology` there before quoting any ratio.

## Layout

| path | what it is |
|---|---|
| `ladder/` | the run at five repetition depths, with per-rung manifests, trust blocks and provenance. Self-describing: it carries its own RO-Crate, JSON Schema and checksums |
| `seed-sweep/` | the second stability axis: the same suite at one fixed repetition depth over 50 independent random seeds, one directory per seed. Also self-describing |
| `figures/` | every figure the repository produces, as vector PDF and 300 dpi PNG, with the script that draws each one and the pinned inputs those scripts read |
| `fecl4/` | the Fe L-edge case study: the two measured spectra (see **Licence** above), the fit and constraint-scenario results, and the scripts |
| `nist_unimplemented/` | the NIST StRD datasets the suite does not yet implement, with the reason for each |
| `references.ris` | the manuscript's bibliography |
| `{CHECKSUMS_NAME}` | SHA-256 of every other file, including the crate |
| `{CRATE_NAME}` | RO-Crate 1.1 description of every file, with the per-file licences |

The directory names mirror `manuscript/examples/` in the repository, deliberately:
the figure scripts resolve their inputs relative to themselves, so
`figures/fig_ladder_stability.py` reads `../ladder/` and `../seed-sweep/`,
`figures/fig_model_graph.py`
reads `../fecl4/` and `figures/fig_nist_catalogue.py` reads
`../nist_unimplemented/`. Renaming a directory here would break them.

## Figures the paper has no room for

The manuscript prints six figures. The repository produces more, and they are all
here at full resolution with their generators. Three in particular are not in the
paper at all:

| figure | what it shows |
|---|---|
| `figures/fig_nist_accuracy.*` | agreement with NIST StRD certified values, per dataset, plotting each dataset's **worst** parameter |
| `figures/fig_nist_catalogue.*` | the whole NIST StRD catalogue, implemented and not, with the reason for each omission |
| `figures/fig_nist_head_to_head.*` | spectrafit-core against lmfit on the implemented NIST datasets, per parameter |

## Verifying

```bash
shasum -a 256 -c {CHECKSUMS_NAME}
```

Or, from a checkout of the repository, which additionally checks that the package
contains exactly what it enumerates and nothing more:

```bash
python3 manuscript/build_fair_package.py --verify .
```

## Redrawing the figures

The pinned inputs are shipped precisely so the figures redraw without a benchmark
run and without network access:

```bash
python3 figures/fig_benchmark_profile.py     # reads figures/bench_summary.json
python3 figures/fig_ladder_stability.py      # reads ladder/ and seed-sweep/
python3 figures/fig_nist_dual.py             # reads figures/nist_head_to_head.json
python3 figures/fig_nist_accuracy.py
python3 figures/fig_nist_catalogue.py
python3 figures/fig_nist_head_to_head.py
python3 figures/fig_model_graph.py           # reads fecl4/fecl4_fit_results.json
python3 figures/fig_architecture.py
```

These need only `matplotlib` and `numpy`.

Three further groups need more than that, and are here for completeness rather
than for a one-command redraw:

- `figures/fig_algorithm_dispatch.py`, `fig_code_compose.py`,
  `fig_code_constraints.py` and `fig_code_benchmark.py` typeset their `.tex`
  sibling with `pdflatex` (with `algorithm2e`) and `pdftoppm`. Their PDF and PNG
  are included, so TeX is needed only to change them.
- `fecl4/fig_constraint_grid.py` and `fecl4/fig_fecl4_case_study.py` re-run every
  fit rather than reading a cache, so they need `spectrafit-core` installed.
- `figures/nist_head_to_head.py`, `nist_table2.py`, `measure_param_agreement.py`
  and `measure_audit_bias.py` are the measurement scripts that *write* the pinned
  sidecars beside them. They need the repository and its test fixtures. Their
  outputs are shipped, so re-running them is a re-measurement, not a prerequisite.

`figures/extract_bench_summary.py` re-derives `bench_summary.json` from a raw run
directory. The per-case payloads that step consumes -- `results.json.gz` and
`audit.json.gz`, tens of megabytes per rung -- are too large to ship and are not
included here or in the repository.
"""


def build(out: Path) -> int:
    """Assemble the package under `out` and return a process exit status."""
    if not LADDER.is_dir():
        print(f"error: no ladder at {LADDER}", file=sys.stderr)
        return 1

    ladder = _read_json(LADDER / "ladder.json")
    name = package_name(ladder)
    target = out / name
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)

    files = collect(target)
    (target / "README.md").write_text(readme(name, ladder))
    files = sorted(p for p in target.rglob("*") if p.is_file())

    # The crate first: it can then carry every payload's digest. Then the
    # checksum manifest over everything including the crate. Between them every
    # file in the package is enumerated exactly once, with nothing left over.
    (target / CRATE_NAME).write_text(
        json.dumps(crate(target, name, files), indent=1) + "\n",
    )
    manifest = sorted(p for p in target.rglob("*") if p.is_file())
    lines = [f"{sha256(p)}  {p.relative_to(target).as_posix()}" for p in manifest]
    (target / CHECKSUMS_NAME).write_text("\n".join(lines) + "\n")

    head = ladder["rungs"][-1]["headline"]
    total = sum(p.stat().st_size for p in manifest) + (target / CHECKSUMS_NAME).stat().st_size
    # `--out` may point outside the repository (a scratch dir, a mount staged
    # for deposit), where `relative_to(ROOT)` raises rather than falling back.
    shown = target.relative_to(ROOT) if target.is_relative_to(ROOT) else target
    print(f"built {shown}")
    print(f"  {len(manifest) + 1} files, {total / 1e6:.1f} MB")
    print(
        f"  geomean {head['geomean_speedup_vs_baseline']:.4f} vs "
        f"{head['baseline_solver_id']}, {head['n_cases']} cases, "
        f"{head['regressions']} regressions, "
        f"reps_effective {ladder['rungs'][-1]['reps_effective']}",
    )
    print(f"  {len(RESTRICTED_FILES)} file(s) carved out of the MIT licence")
    return 0


def verify(target: Path) -> int:
    """Check the package against both its manifests, in both directions.

    A digest check alone is not enough. The failure this also has to catch is a
    manifest that enumerates files which are not there, or a package that carries
    files no manifest mentions -- both of which leave a reader unable to tell what
    the package is supposed to contain.
    """
    manifest_path = target / CHECKSUMS_NAME
    crate_path = target / CRATE_NAME
    if not manifest_path.is_file():
        print(f"error: no {CHECKSUMS_NAME} in {target}", file=sys.stderr)
        return 1
    if not crate_path.is_file():
        print(f"error: no {CRATE_NAME} in {target}", file=sys.stderr)
        return 1

    present = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}
    bad: list[str] = []

    listed: set[str] = set()
    for line in manifest_path.read_text().splitlines():
        if not line.strip():
            continue
        digest, rel = line.split("  ", 1)
        listed.add(rel)
        path = target / rel
        if not path.is_file():
            bad.append(f"checksums lists a missing file: {rel}")
        elif sha256(path) != digest:
            bad.append(f"changed: {rel}")
    # The manifest cannot carry its own digest, and nothing else may be omitted.
    bad += [
        f"present but not in checksums: {rel}"
        for rel in sorted(present - listed - {CHECKSUMS_NAME})
    ]

    graph = json.loads(crate_path.read_text())["@graph"]
    entities = {e["@id"]: e for e in graph}
    dataset = entities.get("./", {})
    parts = {p["@id"] for p in dataset.get("hasPart", [])}
    bad += [f"crate lists a missing file: {rel}" for rel in sorted(parts - present)]
    bad += [
        f"present but not in the crate: {rel}" for rel in sorted(present - parts - {CRATE_NAME})
    ]
    for rel in sorted(parts & present):
        entity = entities.get(rel)
        if entity is None:
            bad.append(f"crate names {rel} as a part but describes no such entity")
        elif "sha256" in entity and entity["sha256"] != sha256(target / rel):
            bad.append(f"crate digest disagrees: {rel}")

    licensed = {rel for rel, e in entities.items() if e.get("@type") == "File" and "license" in e}
    if licensed != set(RESTRICTED_FILES):
        bad.append(
            f"licence carve-out drift: crate marks {sorted(licensed)}, "
            f"expected {sorted(RESTRICTED_FILES)}",
        )

    if bad:
        print(f"{len(bad)} problem(s):", file=sys.stderr)
        for b in bad:
            print("  " + b, file=sys.stderr)
        return 1
    print(f"{target.name}: {len(present)} files")
    print(f"  {len(listed)} checksums match, none missing, none unlisted")
    print(f"  crate describes {len(parts)} parts, exactly what is present")
    print(f"  {len(licensed)} file(s) carry a non-MIT licence, as expected")
    return 0


def main() -> int:
    """Build the package, or verify one that was built earlier."""
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--verify", type=Path, default=None, metavar="DIR")
    args = ap.parse_args()
    return verify(args.verify) if args.verify else build(args.out)


if __name__ == "__main__":
    raise SystemExit(main())
