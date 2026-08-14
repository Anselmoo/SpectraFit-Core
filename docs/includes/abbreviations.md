<!--
Sitewide tooltip glossary (pymdownx.snippets `auto_append`, see zensical.toml).
Each `*[TERM]: definition` line makes TERM render with a dotted underline and
a hover definition wherever it appears as plain prose text on any page (not
inside a code span, not inside a link). These are short, hover-only
one-liners derived from docs/glossary.md — that page remains the canonical,
fuller-prose explanation; do not duplicate its wording verbatim here, and do
not edit glossary.md to keep the two in sync manually.
-->

*[VarPro]: Variable Projection — a solver strategy for separable nonlinear least squares: linear amplitude coefficients are solved analytically, leaving only the nonlinear shape parameters for the outer optimization.
*[DAG IR]: The directed-acyclic-graph intermediate representation models compile to (ModelNodeSpec + ExprEdge), serialized to JSON and evaluated entirely in Rust.
*[DOF]: Degrees of freedom, N_points - N_free (summed across datasets for multi-dataset global fits).
*[AIC]: Akaike Information Criterion, derived from a proper Gaussian deviance term rather than raw chi2.
*[BIC]: Bayesian Information Criterion, derived from a proper Gaussian deviance term rather than raw chi2.
*[ExprEdge]: A graph-level parameter tie added to a fit graph's edge list — one of two equivalent ways to constrain a parameter to another's value or a formula, the other being Parameter.expr.
*[trust-region]: A family of solver strategies (trf, dogleg, newton-cg) that bound each optimization step within an explicit radius rather than taking an unconstrained Gauss-Newton step.
*[PyO3]: The Rust-to-Python FFI framework spectrafit-core uses to expose its Rust kernel as Python functions.
*[Wire string]: The canonical, serialized name for a model type (e.g. gaussian, pseudo_voigt), generated from the Rust model manifest — the source of truth Python's ModelType enum is pinned against.
*[oracle]: An independent reference implementation (lmfit, jax/optimistix, or hand-written numpy formulas) that spectrafit's Rust kernel is cross-verified against.
*[Parameter.expr]: A per-parameter tie set directly on a Parameter's `expr` field — equivalent to an ExprEdge.
*[tied parameters]: Parameters whose value is derived from another parameter or expression on every solver iteration, via ExprEdge or Parameter.expr, rather than being independently optimized.
*[win rate]: The fraction of benchmark cases where spectrafit's fit is faster than the baseline solver.
