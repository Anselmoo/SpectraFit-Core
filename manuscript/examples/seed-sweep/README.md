# sweep-20260816T130505Z

spectrafit-core cross-backend benchmark, run over **50 independent random seeds**
at a fixed repetition depth.

This is the second of the paper's two stability axes, and it answers a different
question from the reps ladder in `../ladder/`. The ladder varies how many times
each case is *timed* and asks whether the measurement settles. This sweep varies
the seed that generates the synthetic data and asks whether the result depends on
the particular draw. Because each seed is an independent realisation, the 50
values are a genuine sampling distribution -- which the ladder's per-case spread
is not, the case catalogue being a fixed hand-designed set rather than a sample.
That is why an interval can honestly be quoted here and not there.

This directory is a self-describing dataset: `ro-crate-metadata.json` (RO-Crate 1.1)
lists every file with its size and SHA-256, `ladder.schema.json` is the JSON Schema
for `ladder.json` and the per-rung `provenance.json`, and `checksums.sha256` lets you
verify the payloads independently of git.

## What is not here

The per-seed `results.json.gz` and `audit.json.gz` payloads are **not** in this
directory, and are not distributed at all: they are too large to ship, and they
stay with the run that produced them. They are deliberately not mirrored here —
the public GitHub mirror is an orphan snapshot branch, so a git-LFS pointer
published here would resolve against a remote that never received the objects,
and a reader would clone a 131-byte stub instead of data. `checksums.sha256` and
`ro-crate-metadata.json` were pruned to drop those payloads rather than name
files a reader cannot fetch.

The same rule removed the 50 per-seed `rungs/seed_*/run.log` entries, which
`.gitignore`'s `*.log` rule keeps out of every clean clone. Nothing is lost with
them: each log is a four-line human-readable rendering of numbers the tracked
`provenance.json` beside it already carries at full precision (`resources`,
`headline`). Both manifests therefore describe exactly the **152** files that
ship, so `sha256sum -c checksums.sha256` verifies clean from a fresh checkout and
`scripts/build_fair_package.py` assembles the same deposit here as on any other
machine — which it now enforces rather than warns about.

Everything needed to redraw the figure is here: `sweep.json` carries the 50
headline geometric means with the host, the resolved comparator versions and the
catalogue fingerprint, and each `rungs/seed_*/manifest.json` carries that seed's
per-case points.

## Results

| `--reps` | effective depth | geomean speedup vs baseline | wall (min) | exit |
|---:|---:|---:|---:|---:|
| 10 | 5 | 15.866 | 17 | 0 |
| 10 | 5 | 15.925 | 13 | 0 |
| 10 | 5 | 16.674 | 22 | 0 |
| 10 | 5 | 16.632 | 15 | 0 |
| 10 | 5 | 15.721 | 12 | 0 |
| 10 | 5 | 16.032 | 15 | 0 |
| 10 | 5 | 15.510 | 11 | 0 |
| 10 | 5 | 16.407 | 15 | 0 |
| 10 | 5 | 16.021 | 15 | 0 |
| 10 | 5 | 16.237 | 14 | 0 |
| 10 | 5 | 15.905 | 15 | 0 |
| 10 | 5 | 16.229 | 17 | 0 |
| 10 | 5 | 15.619 | 15 | 0 |
| 10 | 5 | 15.604 | 15 | 0 |
| 10 | 5 | 15.918 | 14 | 0 |
| 10 | 5 | 16.221 | 19 | 0 |
| 10 | 5 | 15.888 | 10 | 0 |
| 10 | 5 | 16.278 | 15 | 0 |
| 10 | 5 | 15.687 | 15 | 0 |
| 10 | 5 | 16.280 | 17 | 0 |
| 10 | 5 | 15.397 | 13 | 0 |
| 10 | 5 | 15.431 | 15 | 0 |
| 10 | 5 | 16.051 | 13 | 0 |
| 10 | 5 | 16.203 | 14 | 0 |
| 10 | 5 | 16.341 | 18 | 0 |
| 10 | 5 | 15.853 | 12 | 0 |
| 10 | 5 | 15.080 | 21 | 0 |
| 10 | 5 | 15.515 | 14 | 0 |
| 10 | 5 | 15.567 | 18 | 0 |
| 10 | 5 | 16.450 | 16 | 0 |
| 10 | 5 | 16.313 | 13 | 0 |
| 10 | 5 | 16.115 | 10 | 0 |
| 10 | 5 | 15.417 | 15 | 0 |
| 10 | 5 | 15.707 | 16 | 0 |
| 10 | 5 | 15.868 | 12 | 0 |
| 10 | 5 | 16.141 | 14 | 0 |
| 10 | 5 | 16.511 | 8 | 0 |
| 10 | 5 | 15.819 | 9 | 0 |
| 10 | 5 | 15.718 | 18 | 0 |
| 10 | 5 | 15.934 | 12 | 0 |
| 10 | 5 | 16.464 | 15 | 0 |
| 10 | 5 | 15.608 | 10 | 0 |
| 10 | 5 | 16.053 | 18 | 0 |
| 10 | 5 | 16.605 | 9 | 0 |
| 10 | 5 | 15.514 | 17 | 0 |
| 10 | 5 | 15.606 | 13 | 0 |
| 10 | 5 | 16.090 | 14 | 0 |
| 10 | 5 | 16.277 | 15 | 0 |
| 10 | 5 | 15.336 | 11 | 0 |
| 10 | 5 | 15.955 | 14 | 0 |

**The two depths are not the same number.** The suite phase runs
`max(1, reps // 2)` timed solves, so `--reps 25` times each case twelve times. Both
are recorded on every rung; quote `reps_effective`.

## What you need to read the numbers

`ladder.json` carries three blocks that a bare results file does not:

- `config.solvers` — what each backend's solver was told to do. Stopping tolerances
  are **not** normalized across backends; each runs at its own library default.
- `methodology` — the clock, what is inside the timed region, the warmup policy, how
  "recovered" is defined, the dof convention, and the seeds.
- `environment` — machine, kernel limits, thread/BLAS environment, and the `uv.lock`
  digest pinning every transitive dependency.

Also in `config.backend_support`: the backends do **not** all fit the same case set,
so an aggregate is not over an identical set for every backend.

## Provenance

| | |
|---|---|
| host | `terra` — AMD EPYC Processor (with IBPB), 16 cores, 31.3 GiB |
| commit | `0fd4b5d19a1cbd7e5fc4ac5e1f6a07a349fd6ce2` (`fix/jax-compile-budget-max-map-count`), dirty=False |
| python | 3.13.13 |
| generated | 2026-08-17T01:02:23Z |

## Layout

```
ladder.json              aggregate across rungs
ladder.schema.json       JSON Schema, generated from the writing models
ro-crate-metadata.json   RO-Crate 1.1 dataset description
checksums.sha256         digest of every file here
rungs/rung_NNN/
  provenance.json        the rung's full FAIR record
  manifest.json          headline stats
  trust.json             verification ledger
  results.json.gz        the full BenchReport payload (gzip, ~5x)
  audit.json.gz          per-(case, backend) arrays for wire recompute
  run.log                stdout + stderr of the rung
```

Licence: MIT, as the software.
