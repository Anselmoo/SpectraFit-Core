# Scenario-gen reference — realistic benchmark scenarios

Self-contained essentials. Historical specialist content lives in git
history under `.claude/skills/benchmark-scenario-generator/`.

## Scope

Generate realistic benchmark scenarios for spectrafit-core with
constraints, outlier injection, and multi-solver comparisons. Output
is YAML compatible with spectrafit, lmfit, JAX VarPro, and NumPy
solvers.

## Anchored conventions

Adding a new MODEL is a multi-crate change (see `crates-stream §
rust-models.md` and CLAUDE.md §"Adding a New Benchmark Model").
Adding only a **CASE** for an existing model is the cheap path:
a single `CaseSpec`/`CaseFamily` entry in
`python/oracles/cases.py`, under the right category:

| Category | Purpose |
|----------|---------|
| `easy` | clean single-peak Gaussians; should always converge |
| `complex` | multi-peak, overlapping, harder |
| `reality` | datasets resembling real spectra (XPS, IR, NMR, …) |
| `scaling` | large-N (≥1000 points) scaling tests |
| `edge` | edge / ill-conditioned cases (degenerate Jacobians) |
| `lineshapes` | asymmetric, true-Voigt, skewed Gaussian, EMG |
| `optfn` | optimization-function multimodal traps |

## lmfit bound table (CLAUDE.md)

When adding a model with a long-tail shape parameter, add an entry to
`_SHAPE_BOUNDS` in `python/oracles/backends/_lmfit.py`:

| Model | Param | Reason |
|-------|-------|--------|
| pearson7 | `m` | overflow region |
| moffat | `beta` | overflow region |
| students-t | `nu` | overflow region |
| fano | `q` | overflow region |
| asym_ir | `k` | overflow region |

Without the entry, lmfit's LM search drives the parameter into the
formula's overflow region (CX-033 NaN cascade).

## Stuck-mode entry

A scenario that reopens because spectrafit fails but lmfit passes is
usually a starting-value bias or a missing `_SHAPE_BOUNDS` entry.
