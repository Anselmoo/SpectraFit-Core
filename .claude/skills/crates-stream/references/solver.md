# Solver reference — LM / TRF / dogleg / IRLS / Newton-CG / global / varpro

Self-contained essentials for the spectrafit solver family. Historical
specialist content lives in git history under
`.claude/skills/spectrafit-solver/`.

## Architecture (post-faer-rewrite)

The default `solver="lm"` runs the **faer-native LM driver**
(`crates/spectrafit-levenberg-marquardt`, pure-Rust SIMD, no BLAS) on
the `spectrafit-trust-region` framework. `LmProblem`
(`crates/spectrafit-solver/src/problem.rs`) implements the framework's
`TrustRegionProblem` trait. Dispatch (`Solver` enum + single match) and
the universal post-fit stats live in `crates/spectrafit-solver/src/{dispatch,postfit}.rs`.

- **Regime-adaptive step** (`crates/spectrafit-levenberg-marquardt/src/step.rs`):
  `NormalEqLlt` (form `JᵀJ`, Cholesky-solve) for tall-skinny `m≫p`;
  `SvdSecular` (thin SVD + damped solve) for many-parameter / ill-conditioned `p>40`.
- **Post-fit guard** (`postfit.rs::assemble_result`): a fit whose
  user-unbounded free parameter escapes the data-aware domain is downgraded
  to `success=false` with `message="diverged_off_domain"`.
- **faer runs SERIAL** (`faer::set_global_parallelism(Par::Seq)`): Rayon
  thread wake-up dwarfs the work on skinny matrices — 2× win.
- **`lm-legacy`** keeps the old `levenberg-marquardt` (nalgebra) crate as
  a parity oracle. `crates/spectrafit-solver/tests/parity.rs` asserts
  faer `"lm"` ≈ `"lm-legacy"`.

## Solver strategies (Solver::parse → dispatch.rs::fit)

| String | Strategy |
|--------|----------|
| `lm` | faer LM (default), regime-adaptive |
| `lm-legacy` | nalgebra parity oracle |
| `trf` | Trust-Region-Reflective (Coleman–Li `bound_scaling`) |
| `geodesic` | LM + geodesic acceleration |
| `dogleg` | Powell dogleg (Δ-radius) |
| `newton-cg` / `steihaug` | matrix-free Newton-CG |
| `irls:<huber\|bisquare\|cauchy>` | robust IRLS around LM |
| `global` | DE + LM refine; reports `n_de_generations` |
| `varpro` | variable projection (separable, ignores nonlinear bounds) |
| `auto` | structure router |

## What `crates-stream` adds on top

1. **Serena first** for any code touch — `mcp__serena__find_symbol fit`
   before grepping `dispatch.rs`.
2. **Composition** with `superpowers:test-driven-development` — write the
   failing parity test before changing the solver.
3. **Three-pillar reporting** on close — speed (geomean_speedup), rigor
   (max |Δr²| from the parity harness), presentation (N/A for solver
   work unless it changes a contract field).

## Quick paths (kept here for fast scanning)

- LM / regime-adaptive: `crates/spectrafit-levenberg-marquardt/src/step.rs`
  (`StepKind::NormalEqLlt` for tall-skinny, `SvdSecular` for ill-cond).
- TRF: `bound_scaling` flag on the LM driver.
- Dogleg: `crates/spectrafit-dogleg`.
- Newton-CG / Steihaug: `crates/spectrafit-newton-cg`.
- IRLS: `crates/spectrafit-solver/src/irls.rs`.
- Global (DE): `crates/spectrafit-solver/src/global.rs`.
- VarPro: `crates/spectrafit-varpro` (separable, ignores nonlinear bounds).
- Dispatch + post-fit: `crates/spectrafit-solver/src/{dispatch,postfit}.rs`.
- Parity harness: `crates/spectrafit-solver/tests/parity.rs`.

## Stuck-mode entrypoints

If a solver fix reopens twice, `andon-loop/references/stuck-mode.md` kicks
in: curiosity sub-cycle on `dispatch.rs` neighbors, reframe-spike on the
regime selector, or council convene on the LM-vs-TRF dispatch.
