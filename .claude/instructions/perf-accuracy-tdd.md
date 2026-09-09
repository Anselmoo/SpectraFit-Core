# Perf / Accuracy Enforcement Rule

This rule turns a slow or inaccurate `spectrafit` fit into a **BLOCKING**
failure, enforced by `.claude/hooks/enforce-perf-accuracy.sh`.

## The Rule

For every benchmark/quick-validation case where **both** the `spectrafit` and
`lmfit` backends report `success: true`:

- **SPEED** — `spectrafit.timing.median_ms` must **not** exceed
  `2 × lmfit.timing.median_ms`. This mirrors the CLAUDE.md section
  *"Benchmark Backend Comparison Fairness"*: all three backends use
  Levenberg-Marquardt with the same stopping tolerance (`tol=1e-3`), so a fair
  comparison must not let spectrafit drift past 2× lmfit.
- **ACCURACY** — if a per-case current error metric **and** a baseline error
  metric are both present for the `spectrafit` backend, the current error must
  **not** be worse (larger) than the baseline.

Any violating case blocks the operation.

### Threshold

```
spectrafit.timing.median_ms > 2.0 * lmfit.timing.median_ms   -> SPEED violation
spectrafit.<error> > spectrafit.<baseline>                   -> ACCURACY violation
```

The `2.0` factor is the canonical fairness threshold from CLAUDE.md and is the
single source of truth (`SPEED_FACTOR` in the hook).

## Accuracy Field Names (defensive)

Accuracy enforcement is **opt-in by data presence** — it only fires when the
results JSON actually carries both a current and a baseline error figure on the
`spectrafit` backend object. The hook checks, first match wins:

- Current error: `rmse`, `chisqr`, `redchi`, `error`, `residual`
- Baseline error: `baseline_rmse`, `baseline_chisqr`, `baseline_error`,
  `baseline`

If none of these exist, the accuracy check is skipped silently (no false
blocks). Lower values are treated as better.

## Results JSON Structure

```json
{
  "results": {
    "<case_id>": {
      "backends": {
        "spectrafit": { "success": true, "timing": { "median_ms": 52.3 } },
        "lmfit":      { "success": true, "timing": { "median_ms": 20.7 } },
        "jax":        { "success": true, "timing": { "median_ms": 41.0 } }
      }
    }
  }
}
```

## Which results.json?

- If the `RESULTS` environment variable is set, the hook uses that exact file
  (intended for tests / manual runs).
- Otherwise it discovers the newest `results.json` under
  `.spectrafit_reports/quick-validation/` via:

  ```bash
  find .spectrafit_reports/quick-validation -name results.json | xargs ls -t | head -1
  ```

  The search is scoped to the `quick-validation` subtree on purpose: benchmark
  runs also write `results.json` under
  `.spectrafit_reports/benchmark/<date>_run_NNN/`, and we do not want those to
  shadow the quick-validation gate.

- If no results file is found, there is nothing to enforce → the hook passes.

## Exit-Code Contract (Claude Code hook)

- The hook reads the tool-input JSON on **stdin** (it is drained but not used;
  enforcement is driven entirely by `results.json`).
- **exit 2** = BLOCK. A clear per-case reason is written to **stderr**, which
  Claude Code surfaces to the user.
- **exit 0** = pass.
- The hook **never** exits with any other status. Missing files, malformed
  JSON, missing keys, or even a missing `python3` are all normalized to a
  non-blocking pass (exit 0) with a short stderr note, so a flaky environment
  can never wedge the toolchain. The *only* blocking path is an explicit,
  well-formed violation.

## Run It Manually

```bash
# Against the newest quick-validation results:
bash .claude/hooks/enforce-perf-accuracy.sh </dev/null; echo "exit=$?"

# Against a specific file (e.g. a benchmark per-run results.json):
RESULTS=.spectrafit_reports/benchmark/2026-06-02_run_001/results.json \
  bash .claude/hooks/enforce-perf-accuracy.sh </dev/null; echo "exit=$?"
```

`exit=2` means a violation was found (read stderr for the per-case reasons);
`exit=0` means the fairness/accuracy gate passed (or there was nothing to
enforce).

## TDD Loop When It Blocks

1. Read the stderr report; note each `[case_id] SPEED|ACCURACY` line.
2. For a SPEED block, profile the spectrafit solver path for that case (the
   `spectrafit-solver` skill / `crates/spectrafit-solver`) — the goal is
   `spectrafit.median_ms <= 2 × lmfit.median_ms`.
3. For an ACCURACY block, investigate why the fit error rose above baseline
   before touching timing.
4. Re-run the benchmark/quick-validation suite to regenerate `results.json`,
   then re-run the hook manually until `exit=0`.
