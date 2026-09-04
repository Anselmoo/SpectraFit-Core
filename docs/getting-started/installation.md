---
icon: lucide/download
description: Installing spectrafit-core from source with uv and maturin — the only path that works today, since no wheel is published yet — plus the registry commands that will work once the first release is cut.
tags:
  - Python
  - Rust
---

# Installation

## Install spectrafit-core (as a user)

!!! warning "No wheel is published yet — install from source"
    **`spectrafit-core` is not on PyPI.** No version tag has been cut in this
    repository either, so `uv add spectrafit-core` and `pip install
    spectrafit-core` will both fail with "no matching distribution". This is
    the same fact `CITATION.cff` records by deliberately omitting its
    `date-released` field. Until the first release is published, the
    source build below is the only path that works.

Requires **Python $\geq$ 3.13**, plus a Rust toolchain — building from source means
compiling the PyO3 extension yourself. Building also compiles a LAPACK
dependency: `spectrafit-varpro`'s VarPro solver selects `lapack-accelerate`
on macOS and `lapack-netlib` (which needs a Fortran compiler and CMake) on
every other platform (`crates/spectrafit-varpro/Cargo.toml`). What that
means per platform:

- **macOS**: nothing extra to install — `lapack-accelerate` links against
  the OS-provided Accelerate framework.
- **Linux**: a Fortran compiler, CMake, and LAPACK/OpenBLAS headers. This
  project's own CI image installs `build-essential cmake gfortran
  liblapack-dev libopenblas-dev` (`.gitlab/docker/Dockerfile.ci`); the
  GitHub release workflow's manylinux wheel build installs
  `liblapack-dev libopenblas-dev` on top of the manylinux image's own
  toolchain (`.github/workflows/release.yml`).
- **Windows**: unverified by this project's own CI. `.github/workflows/ci.yml`
  (the test suite) has no Windows job, so nothing here has actually been
  tested on Windows. `.github/workflows/release.yml` does build Windows
  wheels, but — unlike its Linux step — installs no Fortran/LAPACK toolchain
  first. Windows wheels are built, not tested; treat Windows support as
  unverified rather than assumed.

```bash
git clone https://github.com/Anselmoo/spectrafit-core.git
cd spectrafit-core
uv sync
uv run maturin develop --release
```

`--release` matters: a debug extension runs 20–50× slower than a release one.
Then run your first fit from inside that checkout — `uv run python -c "import
spectrafit_core"` should import cleanly.

!!! note
    **Status: beta (`0.1.0`).** APIs and the benchmark contract may still
    change before the stable 1.0 release — see the project's `LIMITATIONS.md`
    for currently disclosed gaps.

### Once the first release is published

These are the commands to use as soon as a wheel exists on PyPI; they are
recorded here so this page needs no rewrite at release time, **not** because
they work today — both currently 404 against PyPI, per the warning above.

??? note "Install commands for once a release exists (not live yet)"
    Using `uv` (recommended):

    ```bash
    uv add spectrafit-core
    ```

    Or plain `pip`:

    ```bash
    pip install spectrafit-core
    ```

    At that point no local Rust toolchain will be needed to *use* the
    library — the wheel bundles the compiled Rust core.

Either way, continue to [Quickstart](quickstart.md) to run your first fit.

## Installing for development

If you want to modify spectrafit-core itself (Rust kernel, Python bindings,
benchmark engine, or the web dashboard), you'll need the Rust toolchain and
`maturin` to build the extension locally, plus `uv` to manage the Python
environment. Three steps, run once:

```mermaid
flowchart LR
    A["uv sync"] --> B["maturin develop"]
    B --> C["pytest"]
```

### 1. Sync Python dependencies

```bash
uv sync --extra benchmark
```

Dev tooling (`pytest`, `ruff`, `ty`, the benchmark oracles) is a dependency
group installed by default — this one command is enough, no separate
`--dev` flag needed.

### 2. Build the Rust extension

```bash
uv run maturin develop
```

This compiles `crates/spectrafit-core` (the PyO3 `cdylib`) and installs it
into your `uv`-managed virtualenv as an editable package. Expect a cold
build to take a minute or two; a successful run ends with:

```text
📦 Built wheel for CPython 3.13 to /tmp/.../spectrafit_core-0.1.0-cp313-cp313-macosx_11_0_arm64.whl
✏️ Setting installed package as editable
🛠 Installed spectrafit-core-0.1.0
```

### 3. Run the test suite

```bash
uv run pytest
```

A healthy run ends with a summary line shaped like this (exact counts drift
as the suite grows — the shape is what to expect, not these specific
numbers):

```text
==== 1577 passed, 33 skipped, 4 xfailed, 5 xpassed in 6m11s ====
```

For the full contributor setup — required tool versions, the fast local
lint/test loop, and the MCP-first tooling workflow — see the
[contributor setup guide](../contributor-guide/setup.md).

## Next steps

- **Run your first fit** — [Quickstart](quickstart.md) fits a single Gaussian
  peak in a few lines against the public API, a quicker check that the build
  actually works than the test suite alone.
