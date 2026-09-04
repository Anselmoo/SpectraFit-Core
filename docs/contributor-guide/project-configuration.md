---
icon: lucide/settings
description: How this repository is configured — dependency groups and extras, the build backend, poe task definitions, ruff and ty rule selection, coverage floors, and the version-pinning targets that keep them in step.
tags:
  - Benchmarking
  - CI
  - Python
---

# `pyproject.toml`, explained

`pyproject.toml` is configuration only. Every explanation of *why* a setting has
the value it does lives here, so the file itself stays scannable and the
reasoning stays discoverable to someone who has never opened it.

Most entries below exist to stop a specific regression returning. Where a
decision was verified against a tool at a particular version, the version is
recorded and the check is written out, because a claim about "rrt" is not
checkable and a claim about rrt 1.15.0 is.

The append-only decision log is
[`DECISIONS.md`](https://github.com/Anselmoo/spectrafit-core/blob/main/DECISIONS.md)
in the repository root. This page is the synthesis a contributor reads; that
file records when and why each choice was made.

---

## Dependencies

### Optional extras

`benchmark` installs the comparison oracles. spectrafit is the *subject* under
test (the Rust kernel via `spectrafit_core`); lmfit and JAX/optimistix are
independent cross-verification oracles. The report is served at runtime by the
FastAPI app (`oracles.api`), which is the single source of truth the `web/`
React UI fetches at load time, so `fastapi` and `uvicorn` are part of the
benchmark experience rather than incidental.

`jax` is a **separate** extra because `jaxlib` is a heavy wheel and core CI must
stay fast. The engine degrades gracefully to spectrafit plus lmfit when JAX is
absent; `get_backends` guards it.

### Dependency groups

`manuscript` is kept **out of `dev`** deliberately: matplotlib is a heavy wheel
and nothing in the default dev loop needs to render the paper's figures, so the
group carries its own higher floor (`matplotlib>=3.9`, against `>=3.8`
elsewhere).

matplotlib is *not*, however, unique to the manuscript. It is declared in two
other places and both are exercised: the `benchmark` extra
(`python/oracles/forensics.py` renders per-case diagnostic PNGs, covered by
`tests/unit/oracles/test_forensics_paths.py`) and the `docs` group
(`docs/_render_benchmark_summary.py`, which `poe docs_build` runs before every
`zensical build` — so CI's docs job does need it). What the separate
`manuscript` group buys is a self-contained, version-pinned way to reproduce the
paper's figures from a clean clone, rather than an ad-hoc
`uv run --with matplotlib`:

```bash
uv sync --group manuscript
uv run --group manuscript python manuscript/examples/figures/<fig>.py
```

`docs` duplicates `lmfit` from the `benchmark` extra for the same reason: the
`docs/tutorials/gallery/spectrafit_vs_lmfit_*.py` examples import lmfit directly
as an independent oracle and run as part of `poe docs_build`. Without it a
docs-only sync — which is what both CI docs jobs and `poe docs_build` actually
run — hits `ModuleNotFoundError: lmfit` mid-build.

Notes on individual `dev` entries:

- **`pytest-cov`** covers Python-side branches. The Rust-side `llvm-cov` merge
  wraps the same pytest call under `cargo llvm-cov` instrumentation, so one
  pytest invocation contributes to both `coverage.xml` and
  `target/llvm-cov/lcov.info`. Local reproduction needs
  `source <(cargo llvm-cov show-env --sh)`, then `uv run maturin develop`, then
  `PYTHONPATH=python uv run pytest …`, plus `LLVM_COV` and `LLVM_PROFDATA` on
  macOS.
- **`pytest-xdist`** shards the suite across cores (`-n auto`) so the CI pytest
  job fits under the 3600 s runner cap. The tests are xdist-safe: the
  `.spectrafit_reports` writers all `monkeypatch.chdir(tmp_path)`.
- **`hypothesis`** drives property-based testing, especially the synthetic-data
  invariants.
- **`httpx`** is required by FastAPI's Starlette `TestClient`.
- **`ty`** is floored to match `astral-sh/ty-pre-commit`'s pin, so this project's
  own `ty` and the hook's `ty` are the same version and a diagnostic cannot flip
  between "needed" and "unused" depending on which one runs.
- **`maturin`** is in `dev` because CI's "Build extension" steps call
  `uv run maturin develop`; without it that command fails to spawn.

### Build backend

`[build-system]` requires `maturin`, which compiles the Rust workspace into the
PyO3 extension module the Python package imports. A released wheel ships that
module already built; a source install needs a Rust toolchain.

`[tool.maturin]` points at `crates/spectrafit-core/Cargo.toml` and builds
`spectrafit_core._core` with `pyo3/extension-module`.

---

## Versioning (`rrt`)

### One version group, deliberately

`rrt` supports multi-component versioning: several `[[tool.rrt.version_groups]]`,
each with its own targets, changelog and release branch, bumped independently.
This repository has three plausible components — the Python package, the
eleven-crate Rust workspace, the web dashboard — so the option is real and was
considered.

It is rejected because those three do not release independently. They ship as
one artifact, and a JORS (Journal of Open Research Software) software
metapaper must cite exactly one version, with the archived deposit matching
the version the paper describes. Splitting into groups would institutionalise
the drift this release fixed: `pyproject.toml` at 0.1.0b1, `CITATION.cff` at
0.1.0a1 and the crates at 0.1.0 were three components disagreeing with nobody
noticing.

Revisit only when one component gains its own cadence. The concrete trigger is
publishing the Rust crates to crates.io: a crates.io consumer needs Rust-side
versions that move on Rust-side breaking changes, not on a Python docs fix.

### The canonical version must be semver-parseable

`rrt bump` reads the current version from the **first** target in the group and
parses it with a strict semver 2.0 regex. PEP (Python Enhancement Proposal) 440
pre-release spellings do not match, so while this file said `0.1.0b1` every
`rrt bump` invocation — including `--dry-run` — aborted with
`Invalid semver: '0.1.0b1'`, and the repo could not bump itself at all.

Re-verified against **rrt 1.15.0** (installed, and the latest on PyPI at the time
of writing), so this is upstream behaviour rather than local configuration:

```python
from repo_release_tools.version.semver import Version
Version.parse("0.1.0")         # OK
Version.parse("0.1.0b1")       # ValueError: Invalid semver: '0.1.0b1'
Version.parse("0.1.1-beta.1")  # OK
```

The 0.1.0 release resolves it incidentally, since plain `0.1.0` is valid semver.
If a future pre-release is wanted, spell it semver-style (`0.1.1-beta.1`), not
PEP 440 style, or `rrt bump` breaks again the moment it is written.

### The version targets, and why each is tracked

| target | form | why |
|---|---|---|
| `pyproject.toml` | `kind = "pep621"`, `ci_format = "pep440"` | the canonical version; must be semver-parseable, see above |
| `Cargo.toml` | `section`/`field`, `ci_format = "semver_pre"` | the Rust workspace |
| `CITATION.cff` | pattern | machine-read citation metadata |
| `codemeta.json` | pattern | machine-read citation metadata |
| `web/package.json` | `kind = "package_json"` | the dashboard's surfaced version |
| 5 × "Status: beta (VERSION)" | pattern | live user-facing status text |

**The Rust workspace** was previously untracked, which is exactly why the three
ecosystems drifted: `rrt bump` moved the Python side and left the crates behind.
It uses `section`/`field` rather than `kind = "cargo_toml"` because that kind
targets a plain `[package].version`, and this is a *virtual* workspace root whose
version lives under `[workspace.package]` and is inherited by all eleven member
crates via `version = { workspace = true }`. One target therefore pins the whole
tree. This is the same shape `rrt`'s own autodetect emits for a workspace root.

`ci_format = "semver_pre"` governs `rrt ci-version apply/sync` only — it is never
consulted by `rrt bump`. It matters because Cargo rejects PEP 440 pre-release
spellings, so a CI pre-release stamp must reach the Cargo file as semver
(`0.1.0-beta.1`) while `pyproject.toml` gets `0.1.0b1`.

**The citation files** both carry a version a reader, Zenodo, or a CodeMeta
harvester will believe. `CITATION.cff` had drifted to 0.1.0a1, two bumps behind
pyproject, precisely because nothing tracked it. PEP 440 spelling is correct in
both, since CFF and CodeMeta take an opaque version string.

**`web/package.json`** is `"private": true` so it is never npm-published, but it
declares a version the built dashboard surfaces. The **root** `package.json` is
deliberately *not* tracked: it is also private and declares no version at all,
which is correct for a build-tooling wrapper that is not a released artifact. The
publication-readiness checklist flags its absence; that flag is wrong for this
file, and inventing a version to satisfy it would add a number nothing consumes
and everything could drift from.

**The five status claims** — the README status line, the docs hero badge and
announce banner, `LIMITATIONS.md`'s beta disclosure and the installation-guide
blurb — are live user-facing text. None were tracked, so `rrt bump` would have
left them claiming an old version after a real bump.

Deliberately not tracked: `CHANGELOG.md` (a historical per-release record that
must never be rewritten), `tests/meta/test_version_beta.py` (an intentional
manual regression guard against an accidental alpha revert, not a live claim),
`manuscript/*` and `.claude/docs/**` (frozen point-in-time snapshots), `uv.lock`
(auto-synced by `uv lock`), and the installation guide's two illustrative
CLI-transcript lines (static example output, not a status assertion).

### Folder contract

`[tool.rrt.folders]` is the single source of truth for required structure,
enforced by `rrt folder check` in CI and pre-commit, superseding the old
`scripts/validate_repo_layout.sh`.

`required_*` entries are enforced by `check`, so they must list only committed
source. Gitignored output surfaces belong in `scaffold_dirs`, which `scaffold`
creates but `check` does not enforce, so a fresh checkout never flakes.

The `solver-crate` template is the canonical per-method layout —
`{Cargo.toml, src/{lib,driver,step,problem,tests}.rs}` — so adding a solver
family is a stamp rather than a bespoke decision.

---

## Testing

`xfail_strict = true`: a test marked xfail that actually passes is a **failure**.
It means the feature landed and the stale marker is hiding the test, leaving zero
regression protection.

`addopts = "-m 'not slow'"`: the default run excludes `slow` tests. The
full-history `results.json` round-trip is ~46 MB per run on disk and OOM-kills
the suite. Opt in on an ample-RAM machine with `pytest -m slow`.

Markers: `speedboat` (performance assertions that go red on regression) and
`slow` (end-to-end checks against the real latest benchmark run).

---

## Coverage

Rust has had an 85 % workspace floor since the cjermain merge; Python had **no**
floor at all, so aggregate metrics could rot freely while the gate stayed green.

The Python floor was raised 85 → 94 on 2026-07-25. The original 85 % was set when
measured coverage was near it; coverage has since sat around 94 %, so the old
floor would not have caught a regression until a ~9-point drop. 95 % is the next
target. Keep `.gitlab/30-test.yml` and `.github/workflows/ci.yml`'s
`--cov-fail-under` in sync with `fail_under` here.

Per-module critical-path floors live in the CI configs, not here, and are tighter:
`engine.py` 85 %, `fit.py` 90 %, `evaluate.py` 90 %, `graph.py` 80 %. `poe coverage`
mirrors the CI step and echoes all four.

---

## Type checking (`ty`)

`[tool.ty.src]` scopes `ty`'s project-wide discovery to exactly what
`poe lint_ci` and GitLab's `lint:python` check. This is required because the
`astral-sh/ty-pre-commit` hook invokes `ty` with no path arguments and defers
scope entirely to this config. Without it, a whole-project run surfaces roughly
138 pre-existing diagnostics in `tests/**`, `scripts/*.py` and
`docs/tutorials/gallery/*.py` that no round of the lint-debt cleanup has scoped
in yet.

`allowed-unresolved-imports` lists `jax` and `optimistix` only. They are the
heavy optional backend, deliberately not installed in the fast pre-commit and
core CI jobs, so `ty` cannot resolve them there. Their imports are
runtime-guarded and the engine degrades without them, so a missing module is not
a bug. The suppression is scoped to those globs; a genuinely missing or mistyped
core import still errors. The lighter optional dependencies are installed via
`--extra benchmark` and are really type-checked.

### Rules, and why each is `warn`

Every rule below was verified live against **ty 0.0.65** with
`ty check -c 'rules.<name>="warn"'` before landing, and each is advisory rather
than an error because ty is still pre-1.0.

**Round 1** — from Astral's own "coming from mypy/pyright" guide, both at zero
diagnostics, so pure future-guard:

- `possibly-unresolved-reference` — a name bound only on some control-flow path.
- `unused-ignore-comment` — the ty counterpart to ruff's RUF100: a
  `# ty: ignore[...]` whose diagnostic no longer fires.

**Round 2 (2026-08-09)** — seven more, all at zero diagnostics:

| rule | why it matters here |
|---|---|
| `pydantic-discarded-extra-argument` | a `BaseModel(...)` call with a typo'd kwarg silently swallowed: a real silent-data-loss class in a Pydantic-first codebase |
| `unused-awaitable` | only `oracles/api.py` is async; a missed `await` returns a coroutine silently |
| `possibly-missing-attribute` | typo'd or renamed attribute access surfacing only at runtime |
| `possibly-missing-import` | the same class for module-level imports and re-exports |
| `unsupported-dynamic-base` | a class base ty cannot resolve statically, rare in a `BaseModel`-first codebase |
| `blanket-ignore-comment` | forces a suppression to name what it suppresses |
| `division-by-zero` | statically detectable division by a known zero, in a numerics-heavy codebase |

**Round 3 (2026-08-10)** — the two rules round 2 deferred, closed to zero first:

- `missing-override-decorator` — was 28 hits (17 main, 11 tests). Real
  API-contract value across the six-backend roster, where a subclass method
  meant to override a base method drifts silently.
- `missing-type-argument` — was 91 hits (bare `dict`/`list`). Each needed a real
  generic-parameter decision rather than a mechanical fix; closed in three
  passes.

---

## Linting (`ruff`)

`line-length = 100`, bumped from 88 on 2026-08-10: a `--select ALL` sweep
surfaced many E501 hits in `docs/tutorials/gallery/*.py` and
`docs/_render_benchmark_summary.py` (markdown-embedded prose, f-string table
rows) that were awkward to wrap at 88 without hurting readability. E501 itself is
not selected — line length is enforced by `ruff format`.

`extend-exclude = [".claude", "*.md"]`:

- `.claude` holds harness tooling and generated examples, not shipped library
  source, and is not held to pydocstyle standards.
- `*.md` — `ruff format` reformats Python code blocks embedded in Markdown by
  default, which this repo has never wanted. Narrative docs embed illustrative
  Pydantic snippets with aligned inline comments that ruff would collapse, and
  `docs/tutorials/gallery/*.md` embed a `pymdownx.snippets` directive
  (`--8<-- "script.py"`) inside a ```python fence for highlighting, which
  reformatting mangles into `--8 < --"script.py"` and breaks the site build. The
  `.py` scripts those pages include are **not** excluded and are fully linted.

### How rules are chosen

Every addition was measured against the tree *before* landing, with
`ruff check . --select <CODE> --statistics --exit-zero`, and picked for a real,
low-noise payoff. Rejections are recorded with their measured counts, in
`DECISIONS.md`, rather than silently dropped.

**Round 1** — `D`, `I`, `UP`, `PIE`, `SIM`, `C4`, `RET`, `PTH`, `B`, `ICN`,
`TRY003`, `EM101`, `EM102`. Notes worth keeping:

- `B` — the standout is B905, `zip()` without `strict=`, a silent-truncation
  footgun when array lengths drift. 30 hits measured, not auto-fixable (each
  needs a `strict=True/False` judgement), tracked as manual debt.
- `RUF` — raw count 460, but 409 were RUF001-003 (ambiguous-unicode) firing on
  intentional scientific notation in formula docstrings. Those three codes are
  disabled project-wide; the remaining ~51 are real.
- `TRY003`/`EM101`/`EM102` — 113 hits closed via a `msg = <literal>; raise Exc(msg)`
  extraction across `python/oracles` and `python/spectrafit_core`. The remaining
  38 hits in `scripts/` and `tests/` are carved out per-file, deferred rather
  than forgotten.

Skipped on purpose in round 1: `ANN` (ty already type-checks; a second
annotation-presence linter is redundant) and `ARG` (44 hits, but 18 are the
`lineshapes/*.py` `build(rng, variant)` registry-callback contract where the
shared signature is the point, and 20 more are pytest fixture placeholders — so
ARG is dominated by two structural false-positive patterns here).

**Round 4 (2026-08-10)** — `DTZ`, `NPY`, `FURB`, `LOG`, `G`, `PLW2901`,
`PLC0207`. All at or near zero, locking in conventions the codebase already
follows. Rejected with measured counts: `PD`, `S`, `PLR2004`, `PLC0415`,
`PLR0911`, `PLR0912`, `PLR0913`, `T20`, `SLF`.

**Round 5 (2026-08-10)** — `PERF`, `ISC`, `RSE`, `FLY`, `TID`, `BLE`. Rejected:
`INP001`, `A`, `N`, `SLOT`. Two entries are worth their reasoning:

- `ISC` — zero violations, but a real applicable guard rather than a `PD`-style
  inapplicable zero. This codebase makes heavy deliberate use of *multi-line*
  implicit concatenation for long `Field(description=...)` text;
  `ISC002`'s default `allow-multiline = true` means that is never flagged, and
  only the accidental same-line case is (a missing comma in a list of strings).
  No `ruff format` conflict: the known `ISC001` interaction was checked by
  running both with the rule live.
- `BLE` — zero *new* violations, but not a trivial zero: 14 genuine blind-except
  sites already carried hand-written `# noqa: BLE001` with specific rationale,
  so the rule was being enforced by convention before it was turned on. The one
  bare `except Exception:` without a noqa does not need one, because ruff exempts
  a catch block whose body ends in a bare `raise`.

**Round 6 (2026-08-10)** — the `PT*` cluster: `PT018`, `PT006`, `PT019`, `PT001`.

`PT011` (pytest-raises-too-broad, 14 hits) was measured and **deferred**: every
hit needs a hand-crafted `match=` regex against that site's real error message,
and an imprecise pattern either fails to match (silently breaking the test) or
matches too broadly (defeating the rule).

`TC001`/`TC003` were measured, attempted and **rejected**. Moving a
typing-only-looking import such as `collections.abc.Callable` under
`if TYPE_CHECKING:` broke `PydanticUserError` class-not-fully-defined at
collection time for every `BaseModel` using that name as a field type — this
codebase's core "registry of Pydantic models with `Callable` fields" pattern.
**57 test files failed to collect** before it was caught and fully reverted.

`COM812` (2026-08-10) reverses round 1's own rejection of `COM`, after a
maintainer-run `ruff check . --select ALL --fix` applied it repo-wide across 183
files and `ruff format` converged to a stable fixed point. Only `COM812` is
selected, not the blanket family, since `COM819` is mutually exclusive with it.

> **Note for contributors:** `COM812` and `ruff format` can still undo each
> other on a *newly written* file. Run `ruff format`, then `ruff check --fix`,
> and re-check until stable. `poe lint_ci` runs format first, so a file that
> passed `ruff check` alone can still fail the gate.

### Ignores and carve-outs

`RUF001`-`RUF003` are ignored project-wide: this is a scientific-notation-heavy
codebase by design, not a source of confusable-identifier bugs.

`external = ["FBT003"]`. `FBT` is deliberately **not** selected — real value
across ~18 sites, but a blanket enable was rejected in favour of fixing sites
individually. Four sites are genuine false positives, third-party APIs
(`jax.config.update`, `typer.Option`, matplotlib's `Axes.grid`) whose signatures
require a positional bool, and carry `# noqa: FBT003`. Since FBT003 is never
selected, RUF100 would flag those as dead; `external` tells it the code is a
real, deliberately-unselected rule.

Per-file ignores: tests are self-documenting via their names and are not held to
pydocstyle. `TRY003`/`EM101`/`EM102`/`PERF` are carved out for `scripts/*.py` and
`tests/**/*.py`, where the remaining hits sit outside the scope those rounds
closed.

Docstrings follow the **Google** convention, enforced through ruff's built-in
pydocstyle rather than a separate dependency.

---

## Task runner (`poe`)

`[tool.poe.env]` injects `PYTHONPATH = "python"` into every task.

`_setup_benchmark` is a private helper (the leading underscore hides it from
`poe --help`). Its `maturin develop --release` is **required**: a debug extension
runs 20–50× slower than release, which makes spectrafit lose to pure-Python lmfit
and fails the gate on a build artefact. Accuracy is identical; only timing
collapses.

`lint_ci` mirrors the fast, autofix-free core of `.gitlab/20-lint.yml`'s
`lint:python` — `ruff format --check`, `ruff check`, `ty check`, and an offline
integrity check of the vendored web assets (mermaid, KaTeX, GLightbox), hash-only
by default so the lint gate stays network-free — so a contributor can catch most
of what GitLab would catch without the runner round-trip.

It is **not** byte-for-byte, and the gap is worth knowing: `lint:python` also
runs `poe audit_latex`, then `rrt tree --root . --max-depth 2 --snapshot` and
`scripts/render_architecture_tree.py` followed by a
`git diff --exit-code docs/contributor-guide/architecture.md` that fails when
regenerating the injected tree changes the committed file. A green local
`lint_ci` can therefore still red the pipeline. The `pre-merge-arch-tree`
pre-commit hook covers the tree half; run `uv run poe audit_latex` yourself
before pushing a change that touches maths in `docs/**/*.md`.

`docs_serve` renders the generated pages first, exactly as `docs_build` does.
Without that, `docs_serve` served whatever those files happened to contain while
`docs_build` regenerated them, so the same commit produced a different
performance page depending on which task ran. Both generated targets are
gitignored, so on a fresh clone they do not exist and `zensical serve` would fail
the nav lookup. It uses `shell` rather than `cmd` so the render steps run first,
which means poe does not forward bare CLI arguments — hence the explicit
`--dev-addr` argument declaration.

### Benchmarks

`bench_bg` runs the reps ladder detached, for a workstation that can afford the
wall clock. The citation-grade rung (`--reps 100`) needs roughly 6.8 h by the cost
model measured in `.gitlab/55-deep-bench.yml`, against a 3 h GitLab project
timeout and a shared-runner budget; a local 16-core box has neither limit.

Rungs run **sequentially on purpose**: in parallel they would contend for the
cores whose seconds are the thing being measured.

```bash
uv run poe bench_bg                 # start (default rungs 1,2,5,10,25)
uv run poe bench_bg -- --reps 100   # the citation-grade rung on its own
uv run poe bench_bg_status          # alive? how far along?
uv run poe bench_bg_collect         # rungs -> artifacts/deep/reps-N/
uv run poe bench_bg_stop
```

`bench_bg_collect` writes the same layout `benchmark:deep` uploads, so the figure
scripts consume a local ladder and a CI ladder identically.

The `terra_*` tasks drive the same thing on a dedicated host (16 cores, 31 GiB,
idle) over `nohup` + `setsid`, into a timestamped directory, and fetch it back.
The full suite at reps 25 takes hours: on a shared CI runner that measures
contention as much as the solver, artifacts expire in 30 days, and over a plain
ssh the job dies with the connection. The host name is read from `.env`
(`REMOTE=`), which is gitignored; override with `REMOTE=<ssh-host> REPS=<n> MC=<n>`.

### Manuscript generators

Three tasks keep generated manuscript content from drifting from the code, each
with a `_check` variant that fails rather than regenerating:

| task | regenerates | drift check |
|---|---|---|
| `poe manuscript_deps` | the Availability dependency list, from `pyproject.toml`, the workspace `Cargo.toml` and `web/package.json` | `poe manuscript_deps_check` |
| `poe manuscript_models` | the registered-model inventory table, from `MODEL_REGISTRY` | `poe manuscript_models_check` |
| `python manuscript fair` | the complete reported-run FAIR package (a build product, gitignored) | — |

`scripts/model_inventory.py` refuses to run when a model in `MODEL_REGISTRY` has
no category assigned, so a new model cannot silently vanish from the paper.

### Publish exclusions

`[tool.rrt.publish_targets.github].exclude` is an **allow-list of paths to
strip**, which means anything absent from it ships to the public mirror. A new
top-level directory is published by default. Adding a working-artifact directory
means adding it there *and* to `scripts/publish_exclusions.py`, then re-running
`tests/meta/test_publish_exclusions.py`, which pins the set exactly.

## Next steps

- **See the codebase this tooling builds** — [Architecture](architecture.md)
  covers the directory layout and crate structure the `poe` tasks above
  check, lint, and test.
- **See these settings enforced in CI** — [CI pipeline & cache
  architecture](ci-pipeline.md) covers how the coverage floors and version
  targets described here actually run on GitLab and GitHub.
