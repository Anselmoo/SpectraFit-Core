# ladder-20260815T184025Z

spectrafit-core cross-backend benchmark, run at a ladder of repetition depths.

This directory is a self-describing dataset: `ro-crate-metadata.json` (RO-Crate 1.1)
describes `ladder.json`, `ladder.schema.json` and the per-rung files with their sizes
and SHA-256 digests, but not this README, `checksums.sha256` or itself;
`ladder.schema.json` is the JSON Schema for `ladder.json` and the per-rung
`provenance.json`; and `checksums.sha256` covers every file here except itself, so you
can verify the payloads independently of git.

## Results

| `--reps` | effective depth | geomean speedup vs baseline | wall (min) | exit |
|---:|---:|---:|---:|---:|
| 4 | 2 | 15.971 | 77 | 0 |
| 10 | 5 | 15.785 | 100 | 0 |
| 20 | 10 | 16.159 | 138 | 0 |
| 50 | 25 | 16.364 | 250 | 0 |
| 100 | 50 | 16.446 | 440 | 0 |

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
| commit | `990a4c742e45cc269b9bb15220df5baa8898f58b` (`fix/jax-compile-budget-max-map-count`), dirty=False |
| python | 3.13.13 |
| generated | 2026-08-16T11:25:21Z |

## Layout

```
ladder.json              aggregate across rungs
ladder.schema.json       JSON Schema, generated from the writing models
ro-crate-metadata.json   RO-Crate 1.1 dataset description
checksums.sha256         digest of every file here except itself
rungs/rung_NNN/
  provenance.json        the rung's full FAIR record
  manifest.json          headline stats
  trust.json             verification ledger
```

The full per-case payloads each rung produced — `results.json.gz` and
`audit.json.gz` — are too large to ship here and are not included.

Licence: MIT, as the software.
