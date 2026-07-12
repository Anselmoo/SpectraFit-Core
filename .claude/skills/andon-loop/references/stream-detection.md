# Stream detection: from manifests to a value stream

The goal of Phase 0 is to turn a directory of files into an ordered list of
**stages** and the **wires** between them. This is heuristic — always confirm the
result with the user before building the ledger.

## Step 1 — Find the stages

Each package manifest is a candidate stage:

| Manifest | Language | Stage signal |
|----------|----------|--------------|
| `Cargo.toml` | Rust | a crate (look for `[lib]` with `crate-type` incl. `cdylib` → it feeds an FFI consumer) |
| `pyproject.toml` / `setup.py` | Python | a package; check `[tool.maturin]` or `[build-system]` for a Rust extension |
| `package.json` | JS/TS | a front-end or node service; `vite`/`next`/`react` deps → a web stage |
| `go.mod` | Go | a module |
| `*.csproj` | C#/.NET | a project |
| a directory of scripts with no manifest (e.g. `bench/`) | any | still a stage if other stages import it or read its output |

A directory can be a stage even without a manifest if data flows through it —
your `bench/` is a stage because `core` feeds it and it emits JSON.

## Step 2 — Order the stages and find the wires

Direction of the wire = direction of the dependency / data flow. Detect it from:

- **Build coupling** — `maturin` / `pyo3` / `setuptools-rust` in a Python
  manifest means a **Rust → Python** wire (ABI / extension module).
- **Imports** — `core` is imported by `bench` → a **core → bench** wire (Python
  import-API contract). Grep for `import <stage>` / `from <stage>`.
- **Emitted artifacts** — a stage that writes `*.json` and another that reads it
  → a **producer → JSON → consumer** wire (schema contract).
- **HTTP / fetch** — a front-end that `fetch`es an endpoint the bench/server
  exposes → a **server → web** wire (response-shape contract).

If two stages have no detectable coupling, they are not on the same wire; they
may be parallel sub-streams (see `lanes-and-mcp.md`).

## Step 3 — Tag each wire's lane

| Wire proves something about… | Lane | Why |
|------------------------------|------|-----|
| an ABI call return value | fast / non-visible | call it, assert in-process |
| a Python import contract | fast / non-visible | import + feed a payload |
| a JSON document's shape | fast / non-visible | validate against schema |
| an HTTP response body | fast / non-visible | one request, assert shape |
| a *rendered* UI surface | **slow / visible** | needs a browser (Playwright) |
| a screenshot / visual diff | **slow / visible** | needs rendering + comparison |

Heuristic: **if proving the wire needs pixels, it is the slow lane.** Everything
provable from bytes, types, or JSON is fast. Most wires are fast — which is the
whole reason the loop stays quick even when one stage is a web app.

## The canonical example, fully detected

```
Cargo.toml ([lib] crate-type cdylib)        → stage: crate     (Rust)
pyproject.toml ([tool.maturin])             → stage: core      (Python, wraps crate)
bench/ imports core, writes results.json    → stage: bench     (Python)
results.json read by web                    → artifact wire
package.json (vite + react), fetches JSON   → stage: web       (TS/React)

Wires:
  crate → core   ABI / pyo3          fast
  core  → bench  import API          fast
  bench → json   schema              fast
  json  → web    fetch/shape         fast   ← cheap to keep green every cycle
  web   (render) Playwright          slow   ← cadence / parallel only
```

Note the payoff: only the *rendered* web check is slow. The JSON→web **data**
contract is fast, so most front-end breakage is caught without ever launching a
browser. That is the structural fix for "Playwright is slow."
