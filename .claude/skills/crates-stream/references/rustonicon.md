# Rustonicon reference — Rust/PyO3 idiom review clinic

Distilled from the `rustonicon` standalone skill. Use when the user pastes
Rust code (`.rs`) or a PyO3/maturin interface and asks for review, critique,
or "is this idiomatic?". Runs `zen-of-languages` MCP analysis first as the
objective foundation, then layers Rustic commentary on top. Historical/fuller
content lives in git history under `.claude/skills/rustonicon/`.

## Code analysis workflow (run every time — no exceptions)

1. **Zen of Languages first** — never score or comment before the tool runs:
   - Pasted snippet → `mcp__zen-of-languages__analyze_zen_violations`
   - File/repo path → `mcp__zen-of-languages__analyze_batch_auto`
   - ≥ 10 findings → follow with `mcp__zen-of-languages__generate_prompts`
2. **Map violations to rubric dimensions** (see table below).
3. **Hotspot files first** — if `analyze_batch_auto` flags a hotspot, lead
   with that file's issues even if the user asked about something else.
4. **Layer Rustic commentary on top** — principle name + before/after + *why*.
   Never replace a Zen finding with vague prose; make it more concrete.

| Zen violation category               | Rubric dimension    |
|--------------------------------------|---------------------|
| Panic / unwrap / expect              | Safety              |
| Unnecessary clone / ownership        | Ownership           |
| Iterator / loop / match pattern      | Idiomatic Rust      |
| FFI boundary / GIL / PyO3 type       | PyO3 Interface      |
| Allocation / copy / layout           | Performance         |

## Evaluation rubric (score 1–5; produce a finding for ≤ 3)

| Dimension          | What to examine                                                                     |
|--------------------|-------------------------------------------------------------------------------------|
| **Safety**         | `unwrap()`/`expect()` outside tests, `panic!` at FFI boundary, unjustified `unsafe` |
| **Ownership**      | Unnecessary `.clone()`, owned vs borrowed, lifetime annotations, `Arc`/`Rc` overuse |
| **Idiomatic Rust** | Iterator adapters vs manual loops, exhaustive match, trait impls, newtype pattern   |
| **PyO3 Interface** | GIL handling, `py.allow_threads()`, `PyResult<T>`, typed vs `PyObject` returns     |
| **Performance**    | Allocation patterns, buffer protocol, `&str` vs `String`, `Cow<str>`, stack vs heap |

## Output format (every evaluation uses this structure)

1. **Quick Verdict** — one or two sentences: dominant strength + biggest gap.
2. **Scorecard** — bar-chart text block (`[N/5] ████░`), summed to `/25`.
3. **Findings** — for each dimension ≤ 3: canonical principle name (+ Clippy
   lint if relevant), severity emoji (🔴 correctness/panic/UB, 🟡 maintainability,
   🟢 style), one-line "what's wrong", `// Before` / `// After — Rustic` pair,
   one-line "why this is better." Lead with 🔴 regardless of dimension.
4. **What's Already Good** — one or two genuine strengths; skip if none.
5. **Next Snippet** — close every evaluation with an invitation to submit the next.

## Canonical principle names (use consistently)

| Anti-pattern                                            | Principle name              |
|---------------------------------------------------------|-----------------------------|
| `.unwrap()` / `.expect()` outside `#[cfg(test)]`        | "Propagate with `?`"        |
| `.unwrap()` / `panic!` inside `#[pyfunction]` body      | "Never panic across FFI"    |
| `for i in 0..vec.len()` instead of iterator            | "Chain, don't loop"         |
| `.clone()` where a borrow satisfies the borrow checker  | "Borrow, don't own"         |
| `match` with `_ => ()` discarding unhandled arms        | "Exhaust the pattern"       |
| Missing `#[derive(Debug)]` on structs                   | "Debug everything"          |
| Raw primitives where a newtype adds meaning             | "Newtype over primitives"   |
| `-> PyObject` / `-> Py<PyAny>` where typed return works | "Type the boundary"         |
| CPU-bound loop holding the GIL                          | "Release the GIL"           |
| Copying `Vec<f64>` into Python when buffer suffices     | "Buffer protocol over copy" |
| `Arc<Mutex<T>>` inside `#[pyclass]` body                | "Class-owned state"         |
| `pub fn` accepting `String` that could take `&str`      | "Borrow the boundary"       |
| `From<E>` impl that silently discards context           | "Errors carry context"      |
| `unsafe` block without `// SAFETY:` comment             | "Justify the unsafe"        |

## PyO3 / maturin checklist (flag missing items as ≥ 🟡)

- Every `#[pyfunction]` and `#[pymethods]` body returns `PyResult<T>`
- No `.unwrap()` / `.expect()` inside `#[pyfunction]` / `#[pymethods]`
- CPU-bound sections use `py.allow_threads(|| { ... })`
- `#[pyclass]` structs `#[derive(Debug)]`
- Python-accessible fields use `#[pyo3(get)]` / `#[pyo3(set)]`
- Error types implement `Into<PyErr>` or `.map_err(|e| PyValueError::new_err(...))`
- NumPy arrays use `PyReadonlyArray` / `PyReadwriteArray`, not slice copies
- Module init annotated `#[pymodule]` with name matching `Cargo.toml`'s `lib.name`

## Session loop behaviour

- **Revised code:** re-score only changed dimensions; show delta (`Safety 1/5 → 4/5 ✓`).
- **"What should I fix first?":** point to 🔴 only; if none, lowest 🟡.
- **Score ≥ 22/25:** declare Rustic, offer one optional stretch goal.
- **Snippet > 100 lines:** prioritize `#[pyfunction]` / `#[pymethods]` surface first.
