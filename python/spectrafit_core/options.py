"""Solver-configuration contract for [`spectrafit_core.fit`][spectrafit_core.fit]."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FitOptions(BaseModel):
    r"""Solver configuration for [`fit`][spectrafit_core.fit].

    See ``docs/how-to/choosing-a-solver.md`` for the primary-reference
    citations and per-solver complexity analysis behind the summaries
    below; this docstring deliberately does not duplicate them.

    Attributes:
        schema_version (str): IR schema version (do not change).
        solver (str): Which solver to use.  Supported values, in canonical
            order (``lm`` (default), ``lm-legacy``, ``trf``, ``geodesic``,
            ``dogleg``, ``newton-cg``, ``irls[:huber|bisquare|cauchy]``,
            ``global``, ``varpro``, ``auto``):

            ``"lm"``
                Levenberg-Marquardt (default), on the faer-native trust-region
                core (pure-Rust SIMD, no BLAS).  Regime-adaptive: normal
                equations for tall-skinny problems, SVD for many parameters.
                Fast, gradient-based; best for well-conditioned, unimodal fits.

            ``"lm-legacy"``
                The previous ``levenberg-marquardt`` (nalgebra) implementation,
                retained as a parity/regression oracle.  Slower than ``"lm"``;
                use only to cross-check results.

            ``"trf"``
                The ``"lm"`` core with bound-distance scaling: the damping
                scale of every parameter with two finite bounds is divided by
                $\sqrt{v_i}$, where $v_i \in [10^{-9}, 1]$ is the distance to
                the bound the descent direction points toward over the bound
                span (Coleman–Li), so its steps shrink near that bound.
                Parameters with one or no finite bound have $v_i = 1$; with
                only such bounds ``"trf"`` takes the same steps as ``"lm"``.
                Trial points are projected onto the bounds as in ``"lm"``; it
                is not a trust-region-reflective method.

            ``"geodesic"`` (alias ``"lm-geodesic"``)
                Levenberg-Marquardt with geodesic acceleration (Transtrum).
                Adds a second-order correction; faster on sloppy / degenerate
                surfaces typical of overlapping multi-peak spectra.

            ``"dogleg"``
                Powell's dogleg trust-region method.  Interpolates between the
                Gauss-Newton and steepest-descent steps within an explicit trust
                radius.  Robust, cheap (one Cholesky per iteration); a solid
                alternative to ``"lm"`` on mildly nonlinear fits.

            ``"newton-cg"`` (aliases ``"newton_cg"``, ``"newtoncg"``,
            ``"steihaug"``)
                Matrix-free Newton-CG (Steihaug-Toint truncated conjugate
                gradients) trust-region method.  Never forms $J^\mathsf{T}J$ —
                its per-iteration cost scales with the residual count, not the
                squared parameter count — so it is the choice for large-scale /
                many-parameter or ill-conditioned fits.

            ``"irls"`` (i.e. ``"irls:huber"``)
                Iteratively Re-weighted Least Squares with Huber weights.
                Robust against mild outliers.

            ``"irls:bisquare"``
                IRLS with Tukey bisquare weights.  Recommended for heavy
                outlier contamination (> 5–10 % of data points corrupted).

            ``"irls:cauchy"``
                IRLS with Cauchy weights.  Very heavy-tailed noise / extreme
                outliers.

            ``"global"``
                Differential Evolution + LM refinement.  Explores the full
                parameter space before refining with LM.  Use for multi-modal
                surfaces (Ackley, Rastrigin) or when initial guesses are poor.

            ``"varpro"``
                Variable Projection.  Separates linear coefficients from
                nonlinear parameters, solving them analytically at each step.
                Fastest for models where amplitudes are the only linear params.

            ``"auto"``
                Structure-based routing.  Picks ``"varpro"`` when the graph is
                separable with no tied parameters and all nonlinear parameters
                unconstrained (VarPro's preconditions); otherwise uses ``"trf"``
                (the ``"lm"`` core with bound-distance scaling).  Across a representative case per
                scenario family, TRF is the fastest LM-family strategy at top
                accuracy in most problem classes, though the TRF-over-VarPro
                speed result may invert for very large separable
                problems.  Data-dependent strategies (``"global"`` for multimodal,
                ``"irls"`` for heavy outliers) are *not* auto-selected — choose
                them explicitly when the data calls for them.

        max_iterations (int): Solver patience (default 200). The
            function-evaluation budget is ``max_iterations × (n_free + 1)``;
            the LM family stops with a ``max_iterations`` termination when it
            is exhausted. Must be ``>= 1`` — ``max_iterations=0`` would
            silently produce a no-op fit.
        tolerance (float): Convergence tolerance passed to the solver
            (default 1e-8). Smaller values produce tighter convergence at the
            cost of more iterations.  Set to ``0.0`` to use each solver's
            built-in default (the lower bound is inclusive zero for exactly
            this reason).
        delta0 (float | None): Initial trust-region radius $\Delta$ for
            ``"dogleg"`` and ``"newton-cg"``.  ``None`` (default) keeps the
            library default (problem-derived from the initial scaled-gradient
            norm). Set explicitly for research / debugging on ill-conditioned
            problems. Must be strictly positive — a radius of zero blocks all
            trust-region progress. Plumbs through
            ``crates/spectrafit-types::FitOptionsSpec`` to
            ``dispatch.rs::TrustRegionConfig``. Read only on the ``"dogleg"``
            / ``"newton-cg"`` dispatch arm; setting it alongside any other
            ``solver`` (including ``"trf"``) is silently ignored rather than
            raising an error.
        max_delta (float | None): Hard upper bound on the trust-region radius
            for ``"dogleg"`` and ``"newton-cg"``.  ``None`` keeps the library
            default (1e3). Lower values cap step size for noisy / sloppy
            surfaces. Must be strictly positive, for the same reason as
            ``delta0``. Read only on the ``"dogleg"`` / ``"newton-cg"``
            dispatch arm; setting it alongside any other ``solver``
            (including ``"trf"``) is silently ignored rather than raising an
            error.
        eta (float | None): Step-acceptance threshold for ``"dogleg"`` and
            ``"newton-cg"`` — accept the trial step when $\rho > \eta$.
            ``None`` keeps the library default (1e-4).  Lower values accept
            smaller improvements (faster but less robust); higher values
            reject borderline steps. A probability-like ratio, so it is
            bounded to $[0, 0.25)$: the trust-region driver only shrinks
            $\Delta$ when $\rho < 0.25$, so an ``eta >= 0.25`` would open a
            band in which a step is rejected without shrinking the radius,
            and the solver could spin to ``max_nfev`` instead of failing
            cleanly — enforced on the Rust side by a
            ``debug_assert!(eta < 0.25)`` in the trust-region driver. Read
            only on the ``"dogleg"`` / ``"newton-cg"`` dispatch arm; setting
            it alongside any other ``solver`` (including ``"trf"``) is
            silently ignored rather than raising an error.
        jacobian (str): Jacobian source for the Levenberg-Marquardt family
            (``"analytic"`` (default) or ``"finite_difference"``).
            ``"analytic"`` uses each kernel's own Jacobian.
            ``"finite_difference"`` replaces it, for every kernel, with the
            forward difference of the weighted residual vector $r$,
            $J_{ik} \approx (r_i(\theta + h_k e_k) - r_i(\theta)) / h_k$ with
            $h_k = 10^{-7} \max(|\theta_k|, 10^{-7})$ (one residual evaluation
            per free parameter; MINPACK ``lmdif`` uses the same forward
            difference with its own step). It exists to measure
            how much of the solver's speed comes from the analytic Jacobians
            (benchmark backend ``spectrafit_fd``). Honoured by ``"lm"``,
            ``"lm-legacy"``, ``"trf"``, ``"geodesic"``, ``"dogleg"``,
            ``"newton-cg"``, ``"irls"`` and the LM refinement of ``"global"``;
            ``"varpro"`` rejects it, and ``"auto"`` does not route to VarPro
            when it is set.

    """

    schema_version: str = "0.1"
    solver: str = "lm"
    max_iterations: int = Field(default=200, ge=1)
    tolerance: float = Field(default=1e-8, ge=0.0)
    delta0: float | None = Field(default=None, gt=0.0)
    max_delta: float | None = Field(default=None, gt=0.0)
    eta: float | None = Field(default=None, ge=0.0, lt=0.25)
    jacobian: Literal["analytic", "finite_difference"] = "analytic"

    model_config = ConfigDict(extra="forbid")
