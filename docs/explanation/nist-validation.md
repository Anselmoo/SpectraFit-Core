---
icon: lucide/badge-check
description: How spectrafit-core checks itself against the NIST Statistical Reference Datasets — the Start 2 protocol, the significant-figure measure, the 4.0 threshold, and why W8 governs the evidence rung rather than the merge gate.
tags:
  - NIST StRD
  - Validation
  - Benchmarking
---

# NIST StRD Validation

Every other check in this repository is a check the project wrote about itself.
Unit tests encode the behaviour the author expected; regression tests pin
whatever the code did on the day the baseline was taken; the benchmark gate
compares spectrafit-core against reference implementations that are themselves
software, not truth. All of that catches *change*. None of it catches a fitting
routine that has been quietly, consistently wrong since the first commit.

The [NIST Statistical Reference Datasets
(StRD)](https://www.itl.nist.gov/div898/strd/nls/nls_main.shtml) are the
counterweight. NIST publishes a fixed collection of nonlinear least-squares
problems — real measurement data, a stated model, and **certified parameter
values** computed in extended precision with two independent algorithms and
agreed to at least 11 significant digits, together with certified standard
deviations and residual sum of squares. The numbers were not produced here,
cannot be adjusted here, and do not move when this code changes. Reproducing
them is the one piece of evidence in the suite that a passing result cannot
be manufactured by editing the assertion.

The implementation is `python/oracles/audit/nist.py`; the per-dataset fixtures
live in `python/oracles/nist_strd/`. The full agreement table, dataset by
dataset and parameter by parameter, is
[NIST StRD reference](../reference/nist-strd.md) — this page explains what
that table means and how it was produced.

## Scope: 22 datasets, out of 27

The StRD nonlinear-regression collection contains 27 problems. At the current
commit, `_RECIPES` in `python/oracles/audit/nist.py` implements **22** of them:
Gauss1, Gauss2, Gauss3, Lanczos1, Lanczos2, Lanczos3, BoxBOD, Misra1a, Misra1b,
MGH17, Bennett5, MGH09, Eckerle4, Roszman1, DanWood, Kirby2, Hahn1, Thurber,
Rat42, Rat43, Chwirut1 and Chwirut2.

Five are not implemented, and they are named rather than left as a remainder:
**Nelson** needs two predictors and a log-link, **ENSO** is a sum of sinusoids,
and **MGH10**, **Misra1c** and **Misra1d** each need a kernel shared with no
other dataset in the collection. Each is a missing model, not a failing fit.

`NIST_STRD_TOTAL = 27` is defined in `python/oracles/audit/nist.py` and emitted
on the report contract precisely so that the denominator is never quietly
dropped. The honest statement is "22 of 27", and the denominator is the size of
the external universe, not the size of what happens to be implemented here — a
coverage figure computed against its own scope would always read 100 %. lmfit's
own test suite exercises all 27, so on breadth this project is behind by five.

## Method

Each dataset is fitted once, deterministically, through the ordinary public
API — the same `fit()` entry point a user calls, not a special path.

**Starting point.** Every fit starts from NIST's published **Start 2** guess.
NIST supplies two starting vectors per problem: Start 1, deliberately far from
the solution, and Start 2, closer to it. The audit uses Start 2 throughout, and
this is a limitation stated rather than hidden: several of these problems are
not claimed to converge from Start 1 at all. BoxBOD, MGH17, MGH09, Bennett5 and
Lanczos1 each carry a Start 1 test marked as an expected failure (see
[Expected failures](#expected-failures-and-what-they-do-not-prove) below).
Reproducing certified values from the easier of two published starts is a
weaker claim than reproducing them from the harder one, and only the weaker
claim is made.

**Tolerances.** Fits run with `FitOptions(solver="lm", max_iterations=10000,
tolerance=1e-12)`, which the solver dispatch
(`crates/spectrafit-solver/src/dispatch.rs`) expands into
$\mathrm{ftol} = \mathrm{xtol} = \mathrm{gtol} = 10^{-12}$. This is the
tolerance the shipped audit itself runs at, not a tighter one chosen to make
the table look better. The comparison generator
(`manuscript/examples/figures/nist_table2.py`) holds every backend to that same
$10^{-12}$, and the choice runs against spectrafit-core rather than for it:
regenerating at $10^{-15}$ raises spectrafit-core's figure on 20 of the 22 and
lowers none, while the comparators move less.

**Projection back to NIST's parameterization.** spectrafit-core does not fit
NIST's algebra directly. It composes a model graph out of its own kernels, so a
NIST problem is expressed in whichever kernels reproduce it — Gauss1 through
Gauss3 as one `DOUBLE_EXPONENTIAL` node with its second term fixed off plus two
`GAUSSIAN` nodes, the Lanczos family as two `DOUBLE_EXPONENTIAL` nodes, the
Chwirut pair as a single `EXP_OVER_LINEAR` node, and so on. The recovered
parameters are then projected back into NIST's own naming and scaling before
any comparison happens, because the certified values are only meaningful in
NIST's parameterization. The projection is arithmetic on the fitted values:
a Gaussian's NIST width parameter is $\sigma\sqrt{2}$, Eckerle4's certified
$b_1$ is the product $A\sigma$ of two fitted parameters, DanWood's $b_2$ is
$-1/s$ for a fitted shape $s$.

The build and projection helpers in `python/oracles/audit/nist.py` mirror the
scenario tests' own helpers verbatim, so the audit and the tests cannot silently
fit different models and both report success.

## The measure: significant figures of agreement

Agreement is the **log-relative error** (LRE) — for a fitted value $f$ and a
certified value $c$,

$$
\mathrm{LRE}(f, c) = -\log_{10}\!\left(\frac{|f - c|}{|c|}\right)
$$

read as "how many significant figures the two share". Where the certified value
is zero (Lanczos1 has one at machine epsilon) the denominator falls back to the
absolute difference. Exact bit-for-bit agreement would give $+\infty$, which
does not serialize, so the value is capped at 15 — beyond double precision's
useful range anyway.

A dataset's score is the LRE of its **least accurately recovered parameter**,
not the mean. That is deliberate: a mean lets seven good parameters hide one bad
one, and the whole point of a certified reference is to expose the bad one.
`_validate_one` takes `min(p.sig_figs_agreed for p in params)`, and the
validation's headline `min_sig_figs` is in turn the minimum across all datasets
— a worst-of-worst-cases figure.

### Standard errors get the same measure

NIST certifies standard deviations alongside the parameter values, so the same
LRE is applied a second time, comparing spectrafit-core's fitted standard errors
against those certified standard deviations. This checks something the parameter
column cannot: whether the reported *uncertainty* is trustworthy, not just the
reported value.

It is defined on 20 of the 22. Eckerle4 and DanWood carry no such figure,
because there NIST's certified parameter is a **nonlinear** function of a fitted
one — a product $A\sigma$ and a reciprocal $-1/s$ respectively — through which a
single fitted standard error does not propagate by a constant factor. Those
cells are `null` with a machine-readable reason attached, not a fabricated
number.

Where the measure is defined it mostly tracks the parameter agreement, with one
loud exception. On **Lanczos1** the parameter values agree to 8.747 significant
figures while the standard errors agree to **0.599** — less than one. Lanczos1
is three exponentials whose rate constants leave the design matrix close to
rank-deficient, and a poorly determined covariance is expected there. The lesson
generalizes past this dataset: *a fit can succeed while its reported
uncertainties degrade*, and those uncertainties should not be relied on when it
does.

## The threshold, and why 4.0

`NIST_SIGFIG_THRESHOLD = 4.0` (`python/oracles/audit/nist.py`) is the minimum
agreement required for a dataset to count as passing. It is a deliberate
tightening, and the reasoning is worth stating because a threshold nobody
justifies is a threshold nobody can challenge:

- The scenario tests assert 1e-3 relative agreement on the parameters, roughly
  three significant figures.
- The residual-sum-of-squares and $\chi^2$ assertions in those same tests hold
  to 1e-4, roughly four.
- The audit adopts the stricter of the two. Holding parameters to the tolerance
  already demanded of the derived statistics is the conservative choice.

The actual fits clear it with room to spare — the worst dataset in the
22-dataset recomputation agrees to 6.496 significant figures, leaving about two
and a half figures of headroom over a 4.0 bar. That headroom matters more than
the pass itself: a threshold that a real regression would have to travel a long
way to breach is a threshold that will still be meaningful after the code
changes.

## Difficulty tiers

NIST classifies each problem by difficulty, and the implemented 22 span all
three tiers: **8 Lower, 7 Average, 7 Higher**. The tier string is recorded in
each fixture module's docstring in `python/oracles/nist_strd/` and parsed from
there by the table generator, so it stays attached to the data rather than
living in a hand-maintained list.

The tier is NIST's judgement, not this project's, which makes it useful as an
independent difficulty axis: covering only the Lower tier would produce a
flattering table that proved very little. The Higher tier — BoxBOD, Bennett5,
Eckerle4, MGH09, Rat42, Rat43, Thurber — is where a least-squares implementation
is genuinely tested, and where the two datasets discussed under
[Expected failures](#expected-failures-and-what-they-do-not-prove) sit.

## How it compares, honestly

The comparison table
(`manuscript/examples/figures/nist_table2.json`, rendered in
[NIST StRD reference](../reference/nist-strd.md)) runs spectrafit-core,
lmfit's `leastsq`, SciPy's `least_squares(method="lm")` and SciPy's
`least_squares(method="trf")` over all 22 from Start 2 at the same $10^{-12}$.
Two things are true at once, and both belong in any summary of it:

**spectrafit-core clears four significant figures on all 22 — and so does
lmfit.** spectrafit-core's worst case is 6.496 significant figures (Thurber);
lmfit's worst case is 4.630 (Rat43). Both are above the threshold everywhere.
The only sub-four cells in the table belong to SciPy: `method="lm"` at 2.167 and
`method="trf"` at 2.166, both on Hahn1 and on no other dataset. Anyone
describing this result as "no other implementation matches our NIST accuracy"
would be stating something the committed artifact contradicts.

**No solver dominates.** spectrafit-core is the most accurate on 16 of the 22,
SciPy-trf on four, lmfit and SciPy-lm on one each; spectrafit-core is last of
the four on Lanczos1 and nowhere else. And the curves themselves settle nothing:
`manuscript/examples/figures/fig_nist_dual.py` records that spectrafit-core's
and lmfit's fitted curves differ by between 5e-14 and 8e-7 of a dataset's range,
while the parameters recovered from those same curves differ by up to 3.46
significant figures, and by at least one figure on 17 of the 22. That gap is the
actual argument for using certified values at all: a reader comparing plotted
curves would call the two implementations equivalent, and would be wrong.

## Expected failures, and what they do not prove

Two disclosures belong with any reading of the NIST results.

**Seven non-strict expected failures over five datasets.** The scenario suite in
`tests/scenario/nist_strd/` carries `@pytest.mark.xfail(strict=False)` on seven
tests — two in `test_bennett5.py`, one in `test_boxbod.py`, one in
`test_lanczos1.py`, two in `test_mgh09.py`, and one in `test_mgh17.py`. Most
mark Start 1 convergence; the Bennett5 and MGH09 marks cover convergence more
broadly. `strict=False` means exactly what it says: **the build stays green
whether those tests pass or fail.** An XPASS is not reported as a change and an
XFAIL is not reported as a failure, so these seven carry no evidential weight in
either direction. They document known-fragile territory; they do not test it.

**The test suite's exclusions do not reach the shipped number.**
`tests/audit/test_nist_validation.py` defines `_OPTIONAL_DATASETS = {"Bennett5",
"MGH09"}` and skips those two in its "every mandatory dataset passed" assertion.
That exclusion is **local to the test and is never applied** to the value
`python/oracles/audit/nist.py` returns. `run_nist_validation` computes `passed`
as a strict `all()` over every recipe with no exclusion in the production path,
so a Bennett5 or MGH09 regression fails the overall validation, caps the W8
wire, and blocks the rung-5 unlock exactly like any other dataset would. The
narrower test assertion buys the suite tolerance for two known-hard problems; it
buys the shipped claim nothing.

## Two dataset counts, and which is which

There are two NIST figures in circulation in this repository and they are not
interchangeable:

- **22 datasets**, worst-case agreement 6.496 significant figures — recomputed
  at the current commit from `_RECIPES`, and the basis for everything above.
- **10 datasets**, `min_sig_figs: 6.498`, threshold 4.0 — what the *shipped*
  benchmark run's trust ledger actually records for W8
  (`manuscript/examples/ladder/rungs/rung_050/trust.json`). That ledger is older
  and narrower: its W8 evidence line names Gauss1, Gauss2, Gauss3, Lanczos1,
  BoxBOD, Misra1a, Misra1b, MGH17, Bennett5 and MGH09, and nothing else.

The 22-dataset figures are not yet baked into a shipped ledger. **Neither number
should be quoted as the other** — see [Limitations](../limitations.md), which
states the same distinction. The two happen to sit within 0.002 significant
figures of each other, which makes the confusion easy and the discipline more
important, not less.

## Where this sits in the evidence structure

NIST StRD validation is trust-ledger wire **W8**
(`nist_certified_validation`, built in `python/oracles/audit/wires.py`). Its
result carries `n_datasets`, `min_sig_figs` and `threshold_sig_figs`, and it has
three outcomes rather than two: `pass`, `fail`, and `skipped` when the harness
could not run at all — a distinction that keeps an absent check from reading as
a satisfied one.

What W8 governs is the report's **evidence rung**, the V&V maturity ladder in
`python/oracles/trust_ledger.py`. `RUNG_5` is the "independent differential
validation and external replication" end-stop, and `TrustBlock` refuses to
serialize at that rung unless `nist_validation` is present with `passed=True`
*and* the two inferential wires W10 and W11 both pass. There is no pass by
absence at the ceiling.

What W8 **does not** do is gate a merge. It is not a fourth axis of the
benchmark gate; a NIST regression caps how far the credibility ladder can be
climbed rather than turning a run red — the same point
[Why spectrafit-core](../why-spectrafit-core.md) makes about the gate's three
axes. This is a deliberate separation of concerns: the gate answers "did this
change make the software worse", the rung answers "how strong is the evidence
behind what this software claims". Conflating them would let a strong external
result excuse a performance regression, or a routine speed fluctuation
invalidate a certified-value reproduction that is still perfectly valid.

## What this evidence does not cover

Stated plainly, so it is not inferred:

- It says nothing about the five unimplemented StRD problems.
- It is Start 2 only; Start 1 robustness is not claimed.
- It is the LM solver only. The other solver front-ends described in
  [Solver](solver-selection.md) are not exercised against certified values here.
- It is external in its *reference values*, not in its *execution* — NIST
  certified the numbers, but this project runs the comparison on itself. An
  independent group re-running the work would be stronger evidence than this,
  and does not exist yet.
- On Lanczos1 the reported standard errors agree to well under one significant
  figure, so uncertainty quality is demonstrably not uniform across the
  collection.

## Next steps

- **See the full credibility ladder** — [The self-auditing benchmark](self-auditing-benchmark.md)
  covers how this W8 check rolls up with the other numerical and structural
  wires into one rung.
- **Check the other rung requirements this page doesn't cover** — [Significant
  digits & the uncertainty budget](verification-measurements.md) covers the
  significant-digit and uncertainty-budget measurements W8 doesn't make.
