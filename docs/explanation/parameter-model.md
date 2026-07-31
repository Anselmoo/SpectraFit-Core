# Parameter Model

```python
class Parameter(BaseModel):
    value: float                # initial value
    min: float = -inf
    max: float = inf
    vary: bool = True           # False → fixed constant; ignored when expr is set
    expr: str | None = None     # constraint expression; evaluated every solver iteration
    scale: float | None = None  # solver step-size hint; None → |value| or 1.0
```

`name` is the dict key in `ModelNodeSpec.parameters` — not duplicated as a field.

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

Bounds (min, max) are enforced by reflective projection, not clamping: a step
that overshoots a bound is mirrored back into range (`p < lo` → `2*lo - p`,
and symmetrically at `hi`), with an extreme overshoot parked at the violated
bound instead of reflecting past the opposite one. This runs in
`LmProblem::apply_free_params` (`crates/spectrafit-solver/src/problem.rs`),
called from both solver front-ends' `set_params`, not inside `residuals()`.
`scale` is applied as an internal change-of-variables preconditioning: the
solver works on `theta' = theta / scale` (`LmProblem::scales`,
`apply_free_params`/`scale_columns_rowmajor` in
`crates/spectrafit-solver/src/problem.rs`), not forwarded to any external
`x_scale` field — the `levenberg-marquardt` crate this workspace vendors has
no such field.
