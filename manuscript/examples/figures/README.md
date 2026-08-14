# Manuscript figures

Scripts that generate the software metapaper's figures. Each writes a vector PDF
(for submission) and a 300 dpi PNG (for preview) next to itself.

| Script | Figure | Input |
|---|---|---|
| `fig_architecture.py` | Rust/PyO3/Pydantic architecture | none — the layout is authored |
| `extract_bench_summary.py` | *(not a figure)* reduces a run to `bench_summary.json` | a benchmark run directory |
| `fig_benchmark_profile.py` | cross-backend performance profile | `bench_summary.json` |
| `fig_nist_accuracy.py` | agreement with NIST StRD certified values | `bench_summary.json` |

The FeCl4 case-study figure lives with its data in [`../fecl4/`](../fecl4/).

## Reproducing

```bash
uv sync --group manuscript

# no input needed
uv run --group manuscript python manuscript/examples/figures/fig_architecture.py

# the two benchmark figures share one extraction step
uv run --group manuscript python manuscript/examples/figures/extract_bench_summary.py <run-dir>
uv run --group manuscript python manuscript/examples/figures/fig_benchmark_profile.py
uv run --group manuscript python manuscript/examples/figures/fig_nist_accuracy.py
```

`<run-dir>` is a directory holding `results.json`, `manifest.json` and
`trust.json` — either a local `.spectrafit_reports/benchmark/<run>/`, or the
`canonical/` directory from a `benchmark:deep` CI artifact.

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
