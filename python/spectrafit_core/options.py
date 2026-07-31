"""Solver-configuration contract for :func:`spectrafit_core.fit`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class FitOptions(BaseModel):
    """Solver configuration for :func:`~spectrafit_core.fit`.

    Attributes:
        schema_version: IR schema version (do not change).
        solver: Which solver to use.  Supported values:

            ``"lm"``
                Levenberg-Marquardt (default), on the faer-native trust-region
                core (pure-Rust SIMD, no BLAS).  Regime-adaptive: normal
                equations for tall-skinny problems, SVD for many parameters.
                Fast, gradient-based; best for well-conditioned, unimodal fits.

            ``"trf"``
                Trust Region Reflective.  Levenberg-Marquardt with Coleman–Li
                bound scaling so steps shrink as a parameter approaches an
                active bound.  Use when bounds are active constraints
                (e.g. widths > 0).

            ``"geodesic"``
                Levenberg-Marquardt with geodesic acceleration (Transtrum).
                Adds a second-order correction; faster on sloppy / degenerate
                surfaces typical of overlapping multi-peak spectra.

            ``"dogleg"``
                Powell's dogleg trust-region method.  Interpolates between the
                Gauss-Newton and steepest-descent steps within an explicit trust
                radius.  Robust, cheap (one Cholesky per iteration); a solid
                alternative to ``"lm"`` on mildly nonlinear fits.

            ``"newton-cg"`` (aliases ``"steihaug"``, ``"newton_cg"``)
                Matrix-free Newton-CG (Steihaug-Toint truncated conjugate
                gradients) trust-region method.  Never forms ``JᵀJ`` — its
                per-iteration cost scales with the residual count, not the
                squared parameter count — so it is the choice for large-scale /
                many-parameter or ill-conditioned fits.

            ``"lm-legacy"``
                The previous ``levenberg-marquardt`` (nalgebra) implementation,
                retained as a parity/regression oracle.  Slower than ``"lm"``;
                use only to cross-check results.

            ``"varpro"``
                Variable Projection.  Separates linear coefficients from
                nonlinear parameters, solving them analytically at each step.
                Fastest for models where amplitudes are the only linear params.

            ``"global"``
                Differential Evolution + LM refinement.  Explores the full
                parameter space before refining with LM.  Use for multi-modal
                surfaces (Ackley, Rastrigin) or when initial guesses are poor.

            ``"irls"``
                Iteratively Re-weighted Least Squares with Huber weights.
                Robust against mild outliers.

            ``"irls:bisquare"``
                IRLS with Tukey bisquare weights.  Recommended for heavy
                outlier contamination (> 5–10 % of data points corrupted).

            ``"irls:cauchy"``
                IRLS with Cauchy weights.  Very heavy-tailed noise / extreme
                outliers.

            ``"auto"``
                Structure-based routing.  Picks ``"varpro"`` when the graph is
                separable with no tied parameters and all nonlinear parameters
                unconstrained (VarPro's preconditions); otherwise uses ``"trf"``
                (Coleman–Li bound-scaled LM), which the solver bake-off found to
                be the fastest, most accurate LM-family strategy across problem
                classes.  Data-dependent strategies (``"global"`` for multimodal,
                ``"irls"`` for heavy outliers) are *not* auto-selected — choose
                them explicitly when the data calls for them.

        max_iterations: Maximum solver iterations (default 200).
        tolerance: Convergence tolerance passed to the solver (default 1e-8).
            Smaller values produce tighter convergence at the cost of more
            iterations.  Set to ``0.0`` to use each solver's built-in default.
        delta0: Initial trust-region radius `Δ` for ``"dogleg"`` and
            ``"newton-cg"``.  ``None`` (default) keeps the library default
            (problem-derived from the initial scaled-gradient norm). Set
            explicitly for research / debugging on ill-conditioned problems.
            Cycle 8.2 binding.
        max_delta: Hard upper bound on the trust-region radius for ``"dogleg"``
            and ``"newton-cg"``.  ``None`` keeps the library default (1e3).
            Lower values cap step size for noisy / sloppy surfaces.
        eta: Step-acceptance threshold for ``"dogleg"`` and ``"newton-cg"`` —
            accept the trial step when ``ρ > eta``.  ``None`` keeps the
            library default (1e-4).  Lower values accept smaller improvements
            (faster but less robust); higher values reject borderline steps.

    """

    schema_version: str = "0.1"
    solver: str = "lm"
    # Cycle 18 — Pydantic bounds on numeric solver knobs. Catch
    # nonsense values at validation time (e.g. max_iterations=0 used to
    # silently produce a no-op fit). `tolerance=0.0` means "use solver
    # default" so the lower bound is inclusive zero. delta0/max_delta
    # must be STRICTLY positive (a trust-region radius of zero blocks
    # all progress); eta is a probability-like ratio in [0, 1).
    max_iterations: int = Field(default=200, ge=1)
    tolerance: float = Field(default=1e-8, ge=0.0)
    # Cycle 8.2 — power-user trust-region knobs for `dogleg` / `newton-cg`.
    # `None` defers to the library default; setting a value plumbs through
    # `crates/spectrafit-types/FitOptionsSpec` → `dispatch.rs::TrustRegionConfig`.
    delta0: float | None = Field(default=None, gt=0.0)
    max_delta: float | None = Field(default=None, gt=0.0)
    eta: float | None = Field(default=None, ge=0.0, lt=1.0)

    model_config = ConfigDict(extra="forbid")
