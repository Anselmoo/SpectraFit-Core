---
icon: lucide/download
---

# Installation

## Install spectrafit-core (as a user)

spectrafit-core ships as a Python wheel with a compiled Rust (PyO3) extension.
Requires **Python ≥ 3.13**.

Using `uv` (recommended):

```bash
uv add spectrafit-core
```

Or plain `pip`:

```bash
pip install spectrafit-core
```

!!! note
    **Status: beta (`0.1.0b1`).** APIs and the benchmark contract may still
    change before the stable 1.0 release — see the project's `LIMITATIONS.md`
    for currently disclosed gaps.

That's it for everyday use — the wheel bundles the compiled Rust core, so no
local Rust toolchain is needed to *use* the library. Continue to
[Quickstart](quickstart.md) to run your first fit.

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
📦 Built wheel for CPython 3.13 to /tmp/.../spectrafit_core-0.1.0b1-cp313-cp313-macosx_11_0_arm64.whl
✏️ Setting installed package as editable
🛠 Installed spectrafit-core-0.1.0b1
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
