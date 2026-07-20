# Failure-Kind Taxonomy

Classify EVERY find before fixing — this is what stops thrashing on the wrong layer.

| kind | diagnostic signature | response |
|------|----------------------|----------|
| `infra-flake` | CI/Docker/network non-determinism; passes on retry; unrelated to the diff | retry / report; do NOT edit code. Confirm by re-running. |
| `env-limit` | runner timeout cap, disk ENOSPC, OOM-kill, cgroup limit | config/infra fix (split the job, raise/relocate budget), not logic |
| `instance` | one wrong value/line; root cause is local; no siblings | → `superpowers:systematic-debugging` (4 phases) |
| `class` | symptom of a missing/violated invariant; siblings exist elsewhere | → `big-picture-driven-development` (MAP→…→SWEEP) |
| `stale-contract` | generated artifact drift (openapi.gen.ts, schema, baseline) | regenerate from source; never hand-edit the generated file |
| `external` | upstream dependency bug; reproduces in a minimal repro outside our code | pin/workaround + report upstream; do not contort our code around it |

## Discriminators (when two kinds look alike)
- **infra-flake vs env-limit:** flake passes on identical retry; env-limit fails
  deterministically at the same resource wall (same 60m, same OOM).
- **instance vs class:** ask "if I grep the codebase, are there siblings with the
  same shape?" One → instance. Many → class (fix the class, not the one).
- **our-code vs external:** can you reproduce it in a minimal standalone repro with
  none of our code? Yes → external.

## Worked example (this repo)
`test:python` red at exactly 60m on every run → `env-limit` (GWDG runner caps at
3600 s), NOT `instance`. The fix was splitting the job, not editing test code.
Treating it as an instance bug would have wasted the session in the wrong layer.
