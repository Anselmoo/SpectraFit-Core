# Research brief — The Self-Auditing Benchmark (spectrafit-core)

- **Date:** 2026-06-12
- **Stage:** ideation output (research-pitch-shaper). Feeds the dashboard design
  brainstorm and, later, `scientific-manuscript-drafter`.
- **Grounding run:** `2026-06-11_run_024` — 139 cases, 6 backends
  (spectrafit, lmfit, jax, scipy-ls-lm/trf/dogbox), geomean speedup 12.08× vs
  lmfit baseline, max |Δr²| 1.30e-4, win-rate 86.3%, 0 regressions, gate PASS,
  `saturated_categories = [complex, easy, edge, lineshapes, reality, scaling]`
  (6 of 7; only `optfn` discriminates).

## Chosen angle
**Candidate thesis [→ drafter Phase 1]:** *A cross-backend curve-fitting
benchmark built by the authors of the solver it promotes can silently flatter
its own subject; we present a self-auditing protocol — independent parity
oracle, timing-isolation guards, winner-formula disclosure, saturation honesty,
and a render-truth provenance grammar — and demonstrate it on a 6-backend ×
139-case spectroscopic suite in which it caught and corrected four real
self-deception bugs in our own apparatus.*

**Contribution type:** methodology (protocol + V&V grammar) — with a software
artifact (the interactive dashboard) as the reproducible demonstration.

## Significance [→ drafter Phase 1]
**Why it matters / "wow":** Benchmarks are how the field anoints "faster/better"
solvers, yet the benchmark apparatus is rarely itself audited — and when the
apparatus is authored by the subject's own team, the failure modes are
systematic, not random. We name those failure modes, give a protocol that
detects them, and make every reported number carry its provenance
(measured / derived / reconstructed / absent) so a reader can see *which* claims
are load-bearing. The honesty is the result, not a disclaimer.

**Incremental-risk note:** **Medium.** "Benchmarks can be biased" is not new in
the abstract; novelty rests on (a) a concrete *taxonomy* of self-deception
failure modes for numerical-solver benchmarks, (b) the render-truth provenance
grammar as an enforced, visible channel, and (c) lived before/after evidence of
four caught bugs. Framed as generic "be careful with benchmarks," it is
incremental; framed as a *reusable, enforced protocol with an audit trail*, it
is novel.

## Narrative arc [→ drafter Phase 1]
**Two-part centre:** Part 1 — the threat model + protocol (how a self-built
benchmark deceives itself, and the five guards that prevent it). Part 2 — the
demonstration: four caught-and-corrected bugs with before/after numbers, shown
through a dashboard where provenance is a first-class visual channel.

## Research space (CARS)
- **Territory:** Cross-backend benchmarking (FitBenchmarking and similar) is the
  standard route to claim a new fitting solver is faster or more accurate;
  spectroscopy fitting increasingly spans Rust / Python / JAX backends.
- **Niche:** *…but existing frameworks compare solvers without auditing whether
  the comparison itself is fair or whether the reported numbers are measured.*
  None detect unfair timing rigs, silently dropped features, speed-dominated
  "winner" formulas at accuracy saturation, or reconstructed-as-measured
  convergence/uncertainty values. FitBenchmarking: no saturation analysis, no
  provenance, no Rust solvers.
- **Occupy:** Here we show a self-skeptical protocol that detects and *discloses*
  these failure modes, demonstrated on a suite where we caught four of them in
  our own apparatus and corrected them in the open.

## Novelty / prior-art plan
- **Searches to run:** "benchmark fairness numerical optimization solver";
  "provenance of benchmark results measured vs reconstructed"; "self-reported
  benchmark bias scientific software"; FitBenchmarking papers; BenchScope
  (arXiv 2603.29357) for the saturation/discriminative-power framing;
  reproducibility-in-RSE venues.
- **Closest known work to differentiate from:** FitBenchmarking (compares, does
  not audit); AI-eval benchmark-saturation literature (different domain, no
  provenance grammar); general reproducibility checklists (not enforced/visible
  per-number).
- **Duplication risk:** **medium** — must clearly differentiate from
  FitBenchmarking and from generic reproducibility guidance.

## Minimal Viable Paper (self-demonstration scope)
| Need to demonstrate the thesis | Status |
|---|---|
| Taxonomy of benchmark self-deception failure modes (generalizable) | NEED (synthesize from the 4 bugs) |
| The 4 caught bugs, each with before/after numbers | HAVE artifacts; NEED before-number capture (timing rig, expr_edges drop, winner-formula-at-saturation, vacuous trust wires) |
| Independent parity oracle (numpy) demonstrably independent of subject | HAVE (oracle-independence audit) |
| Render-truth provenance grammar, enforced + visible per number | PARTIAL (grammar designed in prior gen-3 work; must be the dashboard's spine) |
| Saturation honesty (winner is near-meaningless on 6/7 categories) | HAVE (`saturated_categories` flag in manifest) |
| Dashboard as reproducible demonstration artifact | NEED (this build) |

**Falsification:** if the four "bugs" are not reproducible as before/after
deltas (i.e., the corrected numbers are indistinguishable from the originals),
the self-deception claim collapses to "we tidied some code." The before-state
must be recoverable from git history and quantifiable.

## Anticipated figures [→ drafter Phase 1 / figure inventory]
- **Money figure:** the **render-truth panel** — the same headline result shown
  *before* auditing (flattering/rigged) vs *after* (honest), every value tagged
  measured / derived / reconstructed / absent. Liquid glass makes provenance the
  primary visual channel.
- **Supporting 1:** failure-mode taxonomy table (mode → how it deceives →
  guard that catches it → the caught instance).
- **Supporting 2:** saturation map (categories × backends; why "winner" carries
  no accuracy signal on 6/7 categories, only speed).

## Candidate venues (by scope, not impact factor)
- A research-software-engineering / reproducibility venue (e.g. a software &
  computational-methods track) — they would read the contribution as an enforced
  benchmark-integrity protocol with an artifact.
- An analytical-/chemometrics-informatics venue — domain framing via the
  spectroscopic suite; provenance grammar as the transferable idea.
- JOSS/SoftwareX as a companion software paper for the dashboard artifact (the
  protocol paper is the primary; the tool paper is secondary).

## Handoff
Two handoffs, in order:
1. **Now → dashboard design brainstorm.** The money figure (render-truth panel)
   and the two supporting figures define what the liquid-glass dashboard must
   render. Design with `cupertino-council` (principled liquid-glass UI),
   `ground-truth` (V&V claim→evidence map for every number), and
   `test-driven-development` (scientific quality gate), then `writing-plans`.
2. **Later → `scientific-manuscript-drafter`.** Its Phase 1 reads the thesis,
   arc, significance, and figure list above; Phase 0 ingests the dashboard +
   results.json + DECISIONS.md audit trail.
