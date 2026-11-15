---
icon: lucide/sliders
description: The Parameter model's fields (value, min/max, vary, expr, scale), the three binding kinds they compile to, and how bounds are enforced (projected onto the box by the faer LM family, reflected by lm-legacy, dogleg and newton-cg).
tags:
  - Models
  - Solvers
---

# Parameter Model

```python
class Parameter(BaseModel):
    value: float                # initial value
    min: float = -inf
    max: float = inf
    vary: bool = True           # False → fixed constant; ignored when expr is set
    expr: str | None = None     # constraint expression; evaluated every solver iteration
    scale: float | None = None  # solver step-size hint; None → 1.0 (identity, no-op)
```

`name` is the dict key in `ModelNodeSpec.parameters` — not duplicated as a field.

!!! note "`vary` is ignored when `expr` is set"

    `vary` is **ignored** whenever `expr` is set — the engine always derives the
    value from the expression and excludes the parameter from the free set
    regardless of `vary`'s value. There is no validator requiring `vary=True`
    when `expr` is set; `vary` simply has no effect in that case.

Three binding kinds resolved at compile time (`free_mask = vary AND expr is
None`, `spectrafit-graph::compiler`):

| Kind    | vary  | expr | Behaviour                                    |
|---------|-------|------|-----------------------------------------------|
| Free    | True  | None | Element of the optimisation vector           |
| Fixed   | False | None | Constant; never updated                      |
| Expr    | any   | set  | Derived from expression every iteration (Rust `TiedPlan`) — `vary` is ignored |

!!! note "Bounds are projected or reflected, depending on the solver"

    How bounds (min, max) are enforced depends on the solver. The faer
    Levenberg–Marquardt family (`lm`, `trf`, `geodesic`, `auto` when it does not
    route to VarPro, and the LM refinement inside `global` and `irls`) projects
    every trial point onto the box: a step that overshoots a bound is clamped onto
    it. A parameter on a bound whose descent direction points out of the box is
    then held there by the active-set step, which solves the damped step for the
    other parameters (module doc of
    `crates/spectrafit-levenberg-marquardt/src/driver.rs`). `lm-legacy`, `dogleg`
    and `newton-cg` instead reflect an overshooting step back into range
    (`p < lo` → `2*lo - p`, and symmetrically at `hi`), with an extreme overshoot
    parked at the violated bound instead of reflecting past the opposite one. The
    reflection runs in `LmProblem::apply_free_params`
    (`crates/spectrafit-solver/src/lm_problem.rs`), called from both solver
    front-ends' `set_params`, not inside `residuals()`; on the faer LM path the
    point already lies in the box, so it changes nothing there.
    `scale` is applied as an internal change-of-variables preconditioning: the
    solver works on `theta' = theta / scale` (`LmProblem::scales`,
    `apply_free_params`/`scale_columns_rowmajor` in
    `crates/spectrafit-solver/src/lm_problem.rs`), not forwarded to any external
    `x_scale` field — the `levenberg-marquardt` crate this workspace vendors has
    no such field.

## See also

- **Related examples**: [`fixed_params.md`](../tutorials/gallery/fixed_params.md)
  (holding a parameter with `vary=False`),
  [`shared_params.md`](../tutorials/gallery/shared_params.md) (binding one
  parameter to another with `expr`),
  [`bounded_fitting.md`](../tutorials/gallery/bounded_fitting.md) (`min`/`max`
  in use).
- **Related explanation**: [Model Composition — DAG IR](model-composition-dag.md)
  (the graph whose nodes declare these parameters).
