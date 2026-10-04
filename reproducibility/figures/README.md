# Figures and measurements

Scripts that draw the published figures and write the measurements behind them.
Each figure script writes a vector PDF and a 300 dpi PNG next to itself; each
measurement script writes a JSON sidecar next to itself.

## Figures

| Script | What it shows | Input |
|---|---|---|
| `fig_architecture.py` | Rust/PyO3/Pydantic architecture | the crate manifests under `crates/` |
| `fig_benchmark_profile.py` | cross-backend performance profile | `bench_summary.json`, `../ladder/` |
| `fig_performance_profile.py` | Dolan-Moré performance profile across backends | `bench_summary.json`, `../ladder/` |
| `fig_ladder_stability.py` | speedup against repetition depth and against random seed | `../ladder/ladder.json` + per-rung manifests, `../seed-sweep/sweep.json` + per-seed manifests |
| `fig_speed_accuracy_joint.py` | speed and accuracy together, per case | `bench_summary.json`, `../ladder/ladder.json`, `../seed-sweep/sweep.json` |
| `fig_nist_dual.py` | NIST datasets, residuals and certified-value agreement | `nist_head_to_head.json`, NIST tiers from `python/oracles/nist_strd/` |
| `fig_nist_head_to_head.py` | spectrafit-core against lmfit: accuracy and evaluations | `nist_head_to_head.json` |
| `fig_nist_accuracy.py` | per-parameter agreement with NIST certified values | `bench_summary.json` |
| `fig_nist_catalogue.py` | all 27 NIST StRD datasets, implemented or not | fixtures in `python/oracles/nist_strd/`, `../nist_unimplemented/datasets.json` |
| `fig_weighted_win.py` | win counts with an equivalence margin | `nist_table2.json`, `bench_summary.json` |

Three floats carry their caption inside the image and are typeset with `pdflatex`
rather than plotted: `fig_algorithm_dispatch.py` (solver dispatch),
`fig_code_compose.py` (the composable model API) and `fig_code_benchmark.py`
(the commands that run the benchmark), each from the `.tex` file of the same
name. Their PDF and PNG are committed, so a reader without TeX is never blocked.

## Measurements

| Script | Output | What it measures |
|---|---|---|
| `nist_table2.py` | `nist_table2.json`, with `--tolerance 1e-15` `nist_table2_tol1e15.json` | all 22 implemented NIST datasets: spectrafit-core, its standard errors, lmfit, SciPy `lm` and `trf` |
| `nist_head_to_head.py` | `nist_head_to_head.json` | spectrafit-core against lmfit on the same 22, with fitted curves |
| `extract_bench_summary.py` | `bench_summary.json` | reduces a benchmark run directory to what the figures read |
| `measure_param_agreement.py` | `param_agreement.json` | parameter recovery across all six backends |
| `measure_audit_bias.py` | `audit_bias.json` | compiled-kernel against plain-array evaluation cost, and kernel parity |
| `measure_se_timer_bias.py` | `se_timer_bias.json` | the standard-error timer asymmetry |

`bench_summary.json`, `param_agreement.json` and `audit_bias.json`, like the
ladder and the seed sweep, are timing measurements from the benchmark host. They
are committed and pinned in `../checksums.sha256` and are **not** regenerated on
another machine: a wall-clock ratio measured elsewhere is a different measurement.

## The NIST tables record their host

The last significant figures of the ill-conditioned NIST fits depend on the
machine, not only on package versions: the CPU's vector instructions, the C
maths library and the LAPACK under SciPy all play a part. `nist_table2.json`
therefore records, next to the lmfit, SciPy and NumPy versions, the
spectrafit-core build and a `host` block (platform, kernel, glibc patch level,
CPU and vector instructions, BLAS/LAPACK built against and loaded). The tables
in this directory were produced on Linux x86-64 with the release's own
manylinux wheel. The v0.1.0 tables, made on macOS arm64 without that record,
are kept in `comparison/macos-arm64/` with an account of how they differ.

## Reproducing

The NIST tables and the figures that read them, from a checkout:

```bash
uv sync --extra benchmark

cd reproducibility/figures
export MPLBACKEND=Agg SOURCE_DATE_EPOCH=1700000000
PYTHONPATH=../../python uv run --no-sync python nist_head_to_head.py
PYTHONPATH=../../python uv run --no-sync python nist_table2.py
PYTHONPATH=../../python uv run --no-sync python nist_table2.py --tolerance 1e-15
for f in fig_nist_dual fig_nist_head_to_head fig_weighted_win fig_nist_catalogue fig_architecture; do
  PYTHONPATH=../../python uv run --no-sync python $f.py
done
```

The scripts write next to themselves, so this overwrites the committed files;
compare with `git diff`. `SOURCE_DATE_EPOCH` fixes the timestamps in the PDF
files, so an unchanged figure is byte-identical. On a host other than the one
`nist_table2.json` records, expect the last digits to differ; the drift is the
point of the `host` block, not a failure.

`uv sync` builds spectrafit-core from source. To regenerate with a released
wheel instead, install it into a fresh environment together with lmfit, SciPy and
NumPy at the versions `nist_table2.json` records, and put only `python/oracles`
on `PYTHONPATH`, so the source package cannot shadow the wheel.

The benchmark figures read the committed sidecar and need no run:

```bash
uv run --group reproducibility python reproducibility/figures/fig_benchmark_profile.py
uv run --group reproducibility python reproducibility/figures/fig_nist_accuracy.py
```

`extract_bench_summary.py <run-dir>` is only for adopting a *new* benchmark run,
where `<run-dir>` holds `results.json`, `manifest.json` and `trust.json`. A full
`results.json` is about 46 MB, nearly all of it per-point curves no figure reads;
the script performs one heavy read and writes the few-kilobyte sidecar the figure
scripts consume.

## Conventions these figures follow

Colour is assigned by the job it does, and the palette is validated rather than
eyeballed. The benchmark profile carries five backend series against a measured
practical ceiling of six: at six, one adjacent pair sits inside the 6–8 ΔE
colour-vision floor band and two hues fall under 3:1 contrast. That is legal only
with secondary encoding, so series identity there is carried three ways — hue, a
distinct dash pattern, and a direct end-of-line label — never by hue alone.

The NIST figure plots each dataset's **worst** parameter, not its mean, and draws
the individual parameters behind it as light ticks. A mean would let one
badly-recovered parameter hide behind seven good ones, which is exactly the
failure a certified-value check exists to catch. Coverage (datasets exercised out
of datasets published) is stated on the figure itself.
