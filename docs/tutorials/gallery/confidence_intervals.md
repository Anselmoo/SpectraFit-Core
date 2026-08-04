---
icon: lucide/ruler
---

# Parameter Confidence Intervals

## Context

**When to use this pattern.** A point estimate and its `stderr` are useful,
but reporting a 95% confidence interval is usually what a downstream
consumer (a paper, a report, a decision) actually needs. This example turns
every fitted parameter's `stderr` into a 95% confidence interval using the
standard normal ("Wald") approximation, and annotates it directly on the
plot for the two parameters most people care about — a peak's `center` and
`amplitude`.

## Quick example

```python
--8<-- "confidence_intervals.py:data"
```

```python
--8<-- "confidence_intervals.py:build_graph"
```

```python
--8<-- "confidence_intervals.py:fit_execution"
```

```python
--8<-- "confidence_intervals.py:confidence_intervals"
```

![Single-peak fit annotated with 95% parameter confidence intervals](_static/confidence_intervals.png)

## What just happened

1. **Fit as usual** — a single Gaussian peak plus a constant background,
   the same shape as [Single-Dataset Fitting](fitting.md).

2. **From `stderr` to a 95% CI** — for each free parameter,
   `ci_95 = value ± 1.959964 * stderr` (`1.959964` is the two-sided 95%
   critical value of the standard normal distribution). This is a **linear
   approximation** around the fitted optimum: it assumes the parameter's
   sampling distribution is well described by a normal distribution with the
   reported variance. That holds well for well-determined, close-to-linear
   problems like this one, but can understate or misshape the true interval
   for a strongly nonlinear or poorly-determined parameter.

3. **Not covered here: profile-likelihood intervals.** A tighter alternative
   traces the actual χ² surface as one parameter is stepped away from its
   optimum, rather than assuming a local quadratic (normal) shape around it.
   That capability is not yet demonstrated by a gallery tutorial — this
   example is scoped to the `stderr`-based Wald interval, which is what
   `FitResult` exposes directly.

4. **Visual reporting** — the fitted curve is plotted as usual, with the
   peak apex's `center` and `amplitude` 95% CIs drawn as error-bar whiskers
   and printed on the plot, alongside a full table (all four free
   parameters) printed to stdout.

## See also

- **Related examples**: [`fitting.md`](fitting.md) (the base single-peak pattern),
  [`varpro_vs_lm.md`](varpro_vs_lm.md) (solver comparison on a separable fit).
- **Reference**: [Solver — Post-fit statistics](../../explanation/solver-selection.md#post-fit-statistics)
  for how `stderr` and `covariance` are derived.
- **API docs**: `FitResult`, `ParameterResult`.
