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
environment:

```bash
uv sync --extra benchmark   # dev tooling is a dependency-group, installed by default
uv run maturin develop      # build the PyO3 extension in place
uv run pytest                # run the test suite
```

For the full contributor setup — required tool versions, the fast local
lint/test loop, and the MCP-first tooling workflow — see the
[contributor setup guide](../contributor-guide/setup.md).
