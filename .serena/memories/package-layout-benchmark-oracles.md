# Package Layout: benchmark/ + oracles/ (post Plans G + H)

As of 2026-06-10 the Python package tree has three top-level packages:

```
python/
├── spectrafit_core/     # PyO3 wheel (Rust-bound, unchanged)
├── benchmark/           # WAS python/extras/bench/ (renamed Plan H)
│   ├── api.py           # FastAPI service
│   ├── cli.py           # Typer spc-bench CLI
│   ├── contract.py      # BenchReport wire format; re-exports SolverMeta from oracles.contract
│   ├── engine.py        # orchestrator; imports oracles
│   ├── migrate.py       # schema migrators
│   ├── reports.py       # run-dir I/O
│   └── backends/        # 5 adapter modules (_spectrafit, _lmfit, _jax, _scipy_ls, _base)
└── oracles/             # WAS python/extras/bench/{cases,synth,models,…} (split Plan G)
    ├── contract.py      # SolverMeta + future shared types (NEW in Plan H)
    ├── cases.py         # CaseSpec/CaseFamily scenario registry
    ├── synth.py         # synthetic data generation
    ├── models.py        # numpy oracle math + MODEL_REGISTRY
    ├── metrics.py       # r2_of, chi2_red_of, rmse_of
    ├── forensics.py     # post-hoc analysis (backends passed via DI, not imported)
    ├── inference.py     # bootstrap_ci, speedup_ci, delta_r2_ci, tost_equivalence, winner_stability, bh_correct
    ├── trust_ledger.py  # TrustBlock, WireResult, CredibilityRung, WireStatus
    ├── migrate.py       # schema migration registry
    └── audit/
        ├── claims.py    # CLAIM_REGISTRY + @register_claim + 16 registered claims
        ├── wires.py     # W1..W7 wire functions
        └── runner.py    # run_audit(run_dir), computes credibility rung
```

## Dependency direction (enforced, not just convention)
`benchmark → oracles → spectrafit_core` (one direction only)
- `oracles/` imports NOTHING from `benchmark/`
- `oracles/forensics.py` receives backends via DI parameter (was an import violation pre-Plan H)
- `oracles/models.py` was fixed to import `SolverMeta` from `oracles.contract` (not `benchmark.contract`)

## Tests layout
```
tests/
├── unit/
│   ├── spectrafit_core/   # wheel internals
│   ├── benchmark/         # contract, migrate, reports
│   └── oracles/           # oracle math, models, cases
├── integration/
│   ├── benchmark/
│   └── oracles/
├── parity/                # Rust↔numpy kernel parity
├── audit/                 # W1..W7 wire truth tests
├── inference/             # bootstrap_ci, speedup_ci, delta_r2_ci, tost, stability, fdr
├── scenario/              # scenario smoke tests
└── e2e/                   # Playwright

```

## Related memories
- `mem:project_overview` — stale (references extras/benchmark; superseded by this memory)
- `mem:style_conventions` — Pydantic-first, registry-over-map conventions still current

## ADR references
- Plan G merge: commit 8e8aa36
- Plan H merge: commit 78369d3
- `docs/_absorb/C1-decisions.md` entries: 2026-06-10 Plan G and Plan H
