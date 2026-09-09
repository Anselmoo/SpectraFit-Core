# Manuscript figures

Scripts that generate the software metapaper's figures. Each writes a vector PDF
(for submission) and a 300 dpi PNG (for preview) next to itself.

### Figures the paper carries

| Script | Figure | Input |
|---|---|---|
| `fig_model_graph.py` | **1** — the declaration ledger: components, declared parameters, expression edges | `../fecl4/fecl4_fit_results.json` + `fecl4_constraint_scenarios.json` |
| `fig_architecture.py` | **2** — Rust/PyO3/Pydantic architecture | none — the layout is authored |
| `../fecl4/fig_constraint_grid.py` | **3** — the Fe L-edge case study | `../fecl4/` |
| `fig_benchmark_profile.py` | **4** — cross-backend performance profile | `bench_summary.json` |
| `fig_ladder_stability.py` | **5** — speedup against repetition depth and against random seed | `../ladder/ladder.json` + per-rung manifests, `../seed-sweep/sweep.json` + per-seed manifests |
| `fig_nist_dual.py` | **6** — NIST cases, residuals and agreement | `nist_head_to_head.json` |

### Floats whose caption is inside the image

| Script | Float | Input |
|---|---|---|
| `fig_algorithm_dispatch.py` | Algorithm 1, solver dispatch | `fig_algorithm_dispatch.tex` |
| `fig_code_compose.py` | Listing 1, the composable model API in use | `fig_code_compose.tex` |
| `fig_code_constraints.py` | Listing 2, constraints and joint fits | `fig_code_constraints.tex` |
| `fig_code_benchmark.py` | Listing 3, reproducing a measured run | `fig_code_benchmark.tex` |

### Figures the paper has no room for

These ship in the FAIR data package rather than the manuscript.

| Script | What it shows | Input |
|---|---|---|
| `fig_nist_accuracy.py` | per-parameter agreement with NIST certified values | `bench_summary.json` |
| `fig_nist_catalogue.py` | all 27 NIST StRD datasets, implemented or not | `../nist_unimplemented/datasets.json` |
| `fig_nist_head_to_head.py` | spectrafit-core against lmfit: accuracy and evaluations | `nist_head_to_head.json` |

### Measurements, not figures

Each writes a pinned JSON that the prose quotes, so a number in the paper can be
re-derived rather than trusted.

| Script | Output | What it measures |
|---|---|---|
| `extract_bench_summary.py` | `bench_summary.json` | reduces a benchmark run directory |
| `nist_table2.py` | `nist_table2.json` | Table 4 — all 22 NIST datasets, four solvers plus sigma, at 1e-12 |
| `nist_head_to_head.py` | `nist_head_to_head.json` | spectrafit-core against lmfit on the same 22 |
| `measure_param_agreement.py` | `param_agreement.json` | parameter recovery across all six backends |
| `measure_audit_bias.py` | `audit_bias.json` | compiled-kernel vs plain-array cost, and kernel parity |

## Reproducing

```bash
uv sync --group manuscript

# no input needed
uv run --group manuscript python manuscript/examples/figures/fig_architecture.py

# needs pdflatex (with algorithm2e) and pdftoppm; the PDF and PNG are committed,
# so a reader without TeX is never blocked and only a regeneration needs them
uv run --group manuscript python manuscript/examples/figures/fig_algorithm_dispatch.py
uv run --group manuscript python manuscript/examples/figures/fig_code_compose.py

# the two benchmark figures share one extraction step
uv run --group manuscript python manuscript/examples/figures/extract_bench_summary.py <run-dir>
uv run --group manuscript python manuscript/examples/figures/fig_benchmark_profile.py
uv run --group manuscript python manuscript/examples/figures/fig_nist_accuracy.py
```

`<run-dir>` is a directory holding `results.json`, `manifest.json` and
`trust.json` — either a local `.spectrafit_reports/benchmark/<run>/`, or the
`canonical/` directory from a `benchmark:deep` CI artifact.

## Why two of these are LaTeX

`fig_algorithm_dispatch` and `fig_code_compose` are typeset by `pdflatex` rather
than plotted by matplotlib: an algorithm float and a syntax-highlighted code
listing are what the venue's papers use, and Word is a poor host for either as
text. Both carry their caption **inside** the image, so `method.md` has no
caption paragraph beneath them; `manuscript-state.json` marks each
`caption_in_image` and the renderer's caption guard honours that flag. Their PDF
and PNG are committed, so a reader without TeX is never blocked.

## Why the extraction step exists

A full `results.json` is ~46 MB, nearly all of it per-point curve and residual
arrays no figure reads. `extract_bench_summary.py` performs one heavy read and
writes a few-kilobyte sidecar; the figure scripts consume that. The repo's
`guard-memory-hazards` hook refuses direct reads of files that size, and it is
right to — loading it once per figure is both slow and a real memory hazard.

`bench_summary.json` **is committed**, and deliberately so: it is the pinned
input that makes Figures 3 and 4 reproducible from a clean checkout, with no
benchmark run and no access to CI artifacts. Run the figure scripts directly.

Regeneration is only for adopting a *new* benchmark run, and needs the run
directory that produced it — either a local `.spectrafit_reports/benchmark/<run>/`
(gitignored) or the `canonical/` directory from a `benchmark:deep` CI artifact
(30-day retention, on the private GitLab instance). Neither is available to an
outside reader, which is precisely why the sidecar is committed rather than
regenerated on demand.

## Conventions these figures follow

Colour is assigned by the job it does, and the palette is validated rather than
eyeballed. The benchmark profile carries five backend series (JAX is excluded — see the
manuscript), against a measured practical ceiling of six: at six, one adjacent
pair sits inside the 6–8 ΔE colour-vision floor band and two hues fall under
3:1 contrast. That is legal only with secondary
encoding, so series identity there is carried three ways — hue, a distinct dash
pattern, and a direct end-of-line label — never by hue alone. Darkening the
palette to clear the warnings was tried and measured worse: the hues trip the
chroma floor (they read grey) and colour-vision separation drops to ΔE 3.8.

The NIST figure plots each dataset's **worst** parameter, not its mean, and
draws the individual parameters behind it as light ticks. A mean would let one
badly-recovered parameter hide behind seven good ones, which is exactly the
failure a certified-value check exists to catch. Coverage (datasets exercised
out of datasets published) is stated on the figure itself, not only in the
caption.
