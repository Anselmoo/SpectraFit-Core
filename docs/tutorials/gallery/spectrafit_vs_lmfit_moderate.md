---
icon: lucide/shield-check
---

# spectrafit vs. lmfit: a moderately complex spectrum

## Context

**Why this example exists.** Every other script in this gallery cross-checks
spectrafit against *itself* — a different solver
([`varpro_vs_lm.md`](varpro_vs_lm.md)), a different parameter surface
([`shared_params.md`](shared_params.md)), a different dimensionality
([`3d_fitting.md`](3d_fitting.md)). This is the first tutorial in this
gallery to include [lmfit](https://lmfit.github.io/lmfit-py/) as an external
cross-check, not just spectrafit's own alternate solvers. lmfit is a
separate, independently-implemented least-squares package — its own
Levenberg-Marquardt driver, its own parameter bookkeeping — so agreement
with it is a genuinely independent oracle in a way agreement between two
spectrafit solvers is not. The project's own benchmark harness
(`python/oracles/`, see
[Benchmark engine](../../contributor-guide/benchmark-engine.md))
uses exactly this idea at scale, running spectrafit against lmfit and
jax/optimistix across a whole case catalog; this example distills that
pattern down to one hand-built, readable script.

**Why this scenario.** The gallery's other examples are deliberately simple
(one or two isolated peaks) so the mechanic being demonstrated stays
front-and-center. This one is intentionally more realistic: four
overlapping peaks of *mixed* shape (two Gaussian, two Lorentzian) sitting on
a sloped linear background — closer to what a real spectrum (XPS, Raman,
UV-Vis, ...) actually looks like than a single clean peak in flat noise.

## Quick example

```python
--8<-- "spectrafit_vs_lmfit_moderate.py:formulas"
```

```python
--8<-- "spectrafit_vs_lmfit_moderate.py:data"
```

```python
--8<-- "spectrafit_vs_lmfit_moderate.py:build_graph"
```

```python
--8<-- "spectrafit_vs_lmfit_moderate.py:build_lmfit"
```

```python
--8<-- "spectrafit_vs_lmfit_moderate.py:report"
```

```python
--8<-- "spectrafit_vs_lmfit_moderate.py:assertions"
```

![4-peak fit (2 Gaussian + 2 Lorentzian + linear background) compared between spectrafit and lmfit](_static/spectrafit_vs_lmfit_moderate.png)

## What just happened

1. **Data creation** — two Gaussian peaks and two Lorentzian peaks, spaced
   closely enough to overlap in their wings, on top of a sloped linear
   background. Both backends are handed the same deliberately-off-true
   starting guesses (a realistic "eyeballed from the plot" starting point,
   not the answer key), so the comparison is apples-to-apples.

2. **Backend 1: spectrafit's own `fit()`** — a 5-node `FitGraph` (4 peaks +
   one `ModelType.LINEAR` background node) built by `build_graph()`, fit
   with the default solver.

3. **Backend 2: a hand-built lmfit composite model** — following the exact
   pattern used by the project's own lmfit oracle backend
   (`python/oracles/backends/_lmfit.py`): one `lmfit.Model(fn, prefix=...)`
   per component, summed with `+`, each component's `.make_params(...)`
   merged into one `Parameters` object, then
   `composite.fit(y, params, x=x)`. The per-peak numpy formulas
   (`gaussian`, `lorentzian`, `linear_bg`) use the same convention as
   `python/oracles/models.py`: `amplitude` is the peak height at `center`
   (not the integrated area), Gaussian `sigma` is the standard deviation,
   and Lorentzian `sigma` is the half-width at half maximum (HWHM) — a bare
   hand-rolled lmfit model that matches spectrafit's own convention exactly,
   rather than lmfit's builtin `GaussianModel`/`LorentzianModel`, which
   normalize by area.

4. **Side-by-side report** — a printed table of `chi2` and measured
   wall-clock time per backend, then a second table comparing all 12 fitted
   parameters (`amplitude`, `center`, `sigma`/`slope`/`intercept` across 4
   peaks + the background) side by side with their absolute difference.

5. **Agreement, asserted not just claimed** — the script asserts every
   fitted parameter agrees between backends to within `1e-4`, and `chi2`
   agrees to within `1e-4` too. In practice, on this problem, both land
   within about `4e-6` of each other — two independently-implemented
   optimizers converging on the same optimum from the same starting point.

## See also

- **Related examples**: [`varpro_vs_lm.md`](varpro_vs_lm.md) (spectrafit's
  own alternate-solver comparison), [`shared_params.md`](shared_params.md)
  (tied parameters), [`fitting.md`](fitting.md) (the simplest single-peak +
  background workflow this example builds on).
- **Reference**:
  [Benchmark engine](../../contributor-guide/benchmark-engine.md)
  (the full `python/oracles/` harness this script's lmfit pattern is drawn
  from), [Choosing a Solver](../../how-to/choosing-a-solver.md).
- **Performance**: the project's own aggregate spectrafit-vs-lmfit speed and
  accuracy comparison across its full benchmark case catalog lives on the
  [Performance](../../performance/index.md) page, not in this gallery
  script — the wall-clock numbers printed here are one small demo problem,
  not a general performance claim.
- **API docs**: `FitGraph`, `ModelNodeSpec`, `Parameter`, `fit`.
