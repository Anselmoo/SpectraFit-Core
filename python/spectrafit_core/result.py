"""Fit-result contracts: fitted parameters, diagnostics, and per-slice data."""

from __future__ import annotations

import math

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from .parameters import ParameterResult


class DatasetSlice(BaseModel):
    """Per-dataset diagnostics for multi-dataset global fits.

    Attributes:
        label (str | None): Optional human-readable label for this slice (may
            be ``None``).
        n_points (int): Number of data points in this slice.
        best_fit (list[float]): Model values at the fitted parameters, length
            ``n_points``.
        residuals (list[float]): Signed residuals ``(y_observed - y_fit)``,
            length ``n_points``.
        chi2 (float): Sum of squared residuals for this slice only.

    """

    label: str | None = None
    n_points: int
    best_fit: list[float]
    residuals: list[float]
    chi2: float

    model_config = ConfigDict(extra="forbid")


class FitResult(BaseModel):
    r"""Result of a single [`fit`][spectrafit_core.fit] call.

    Attributes:
        schema_version (str): IR schema version of the producing engine.
        parameters (dict[str, ParameterResult]): Fitted parameter values and
            uncertainties, keyed by ``"node_id.param_name"`` (dotted
            notation).
        covariance (list[list[float | None]] | None): Parameter covariance
            matrix (row/column order matches ``parameters``), or ``None`` if
            the solver could not estimate it.
        chi2 (float): Total *unweighted* sum of squared residuals
            $\sum_i (y_i - \hat{y}_i)^2$, recomputed at the solution. This is
            deliberately **not** the weighted residual the solver minimises:
            it stays comparable across backends even when a per-point
            ``sigma`` was supplied and used to weight the fit.
        reduced_chi2 (float): ``chi2 / dof``. Because ``chi2`` above is
            unweighted, this is a mean squared residual in the data's own
            units, **not** the textbook $\sigma$-normalised statistic — the
            "values near 1.0 indicate a good fit" reading does *not* apply
            here. See *Post-fit statistics* in the Solver selection
            explanation page.
        r_squared (float): Coefficient of determination $R^2$.
        dof (int): Degrees of freedom ``n_points − n_free``, clamped to a
            minimum of 1 so the reduced statistics stay finite. When the fit
            is exactly determined or over-parameterised the true value is
            $\le 0$ and ``reduced_chi2`` is not meaningful; the clamp keeps
            it finite rather than undefined.
        aic (float): Akaike Information Criterion.
        bic (float): Bayesian Information Criterion.
        n_iter (int): Accepted solver iterations for the faer-native solvers;
            for ``lm-legacy`` the number of function evaluations (that engine
            does not expose iterations). ``varpro`` reports 0 (its engine
            does not expose iterations either).
        n_func_evals (int | None): Number of residual evaluations (``None``
            if unavailable).
        n_jac_evals (int | None): Number of Jacobian evaluations (``None`` if
            unavailable).
        success (bool): ``True`` if the solver converged within
            ``max_iterations``.
        message (str): Stable termination-reason key, not free text — one of
            the strings produced by ``TerminationReason::as_str`` /
            ``faer_termination_str`` (e.g. ``"converged_ftol"``,
            ``"converged_xtol"``, ``"converged_gtol"``, ``"converged"`` for
            lm-legacy, ``"max_iterations"``, ``"no_improvement_possible"``,
            ``"residuals_zero"``, ``"numerical_error"``).
            Three post-fit forms replace or extend the key vocabulary, all
            applied by ``apply_postfit_guards`` in
            ``spectrafit-solver::postfit``:

            - An originally-unbounded free parameter that escaped the
              data-derived domain replaces the key entirely with
              ``"diverged_off_domain (<key>=<val> escaped data domain
              [...])"``, e.g. ``"diverged_off_domain (p1.amplitude=1.234e5
              escaped data domain [-3.900e0, 7.800e0])"``, and downgrades the
              result to ``success=False``.
            - A post-fit guard that detects a collapsed fit ($r^2 < 0$ with a
              near-zero amplitude/height) replaces the key with a
              ``"degenerate_fit (…)"`` string carrying the guard's reason,
              e.g. ``"degenerate_fit (r2=-1.234e0 < 0, peak amplitude
              collapsed)"``.
            - A soft-stop termination (``"no_improvement_possible"`` or
              ``"max_iterations"``) upgraded to success because
              $r^2 \ge 0.9$ instead keeps the original key and appends an
              ``"_accepted_at_r2_<value>"`` suffix, e.g.
              ``"no_improvement_possible_accepted_at_r2_0.9921"``.

            Match on the ``"diverged_off_domain"`` / ``"degenerate_fit"``
            prefix or the original key prefix respectively, rather than the
            whole string — the bracketed/appended part is diagnostic text,
            not a stable key.
        best_fit (list[float]): Model values at the fitted parameters, one
            per data point.
        residuals (list[float]): Signed residuals ``(y_observed - y_fit)``.
        init_fit (list[float]): Model values evaluated at the initial-guess
            parameters.
        components (dict[str, list[float]]): Per-node contributions summing
            to ``best_fit``.
        dataset_slices (list[DatasetSlice] | None): Per-dataset diagnostics
            for multi-dataset fits, ``None`` for single-dataset fits.
        condition_number (float | None): Condition number of $J^\mathsf{T}J$
            at the solution (ratio of largest to smallest singular value).
            Large values flag an ill-conditioned, poorly determined fit.
            ``None`` when the solver did not compute it.
        n_de_generations (int | None): Number of differential-evolution
            generations run before the LM refinement on the
            ``solver="global"`` path. ``None`` for direct LM and other
            solvers. Makes the DE search effort visible, since ``n_iter``
            counts only the post-DE refinement (often 0).
        cost_history (list[float]): Per-iteration cost
            $\frac{1}{2}\|r\|^2$ trajectory from the faer LM / trust-region
            drivers (index 0 = initial point, last = terminal cost). Empty
            for solvers that do not track it (``solver="lm-legacy"`` /
            ``"varpro"``). Observability only — it does not affect the fit.
        gradient_norm_history (list[float]): Per-iteration gradient
            infinity-norm $\|J^\mathsf{T}r\|_\infty$ recorded alongside each
            [`cost_history`][spectrafit_core.FitResult] entry. Empty when not tracked.
            Each entry is the gradient *at the most recent point where the
            Jacobian was evaluated* — the start of that outer iteration — not
            at the point whose cost sits at the same index. When the loop
            stopped after an accepted step the terminal entry therefore
            repeats the previous iteration's gradient; the final entry always
            equals the driver's reported final gradient norm
            (``spectrafit_trust_region::Report::gradient_norm``), which
            ``FitResult`` does not mirror as a scalar.
        params_history (list[list[float]]): Per-iteration free-parameter
            vector $\theta$ recorded alongside each [`cost_history`][spectrafit_core.FitResult]
            entry (same length/order). Raw material for the
            convergence-to-truth metric
            $d_k = \|(\theta_k - \theta_{\text{true}})/s\|_2$ on synthetic
            cases. Empty for solvers that do not track it (only the faer LM
            driver records it today). Observability only.
        covariance_param_order (list[str] | None): Ordered list of
            free-parameter names that index the rows and columns of
            [`covariance`][spectrafit_core.FitResult]. ``covariance[i][j]`` is the covariance
            between ``covariance_param_order[i]`` and
            ``covariance_param_order[j]``.  Use this to look up cross-terms
            by name rather than relying on [`parameters`][spectrafit_core.FitResult] iteration
            order (which is non-deterministic for ``HashMap``-backed dicts).
            ``None`` for payloads produced before the schema added this
            field (backwards-compatible default).

    """

    schema_version: str = "0.1"
    parameters: dict[str, ParameterResult] = Field(
        default_factory=dict,
        validation_alias=AliasChoices("parameters", "params"),
        serialization_alias="parameters",
    )
    covariance: list[list[float | None]] | None = None
    chi2: float = 0.0
    reduced_chi2: float = 0.0
    r_squared: float = 0.0
    dof: int = 0
    aic: float = 0.0
    bic: float = 0.0
    n_iter: int = 0
    n_func_evals: int | None = None
    n_jac_evals: int | None = None
    success: bool = False
    message: str = ""
    best_fit: list[float] = Field(default_factory=list)
    residuals: list[float] = Field(default_factory=list)
    init_fit: list[float] = Field(default_factory=list)
    components: dict[str, list[float]] = Field(default_factory=dict)
    dataset_slices: list[DatasetSlice] | None = None
    condition_number: float | None = None
    n_de_generations: int | None = None
    cost_history: list[float] = Field(default_factory=list)
    gradient_norm_history: list[float] = Field(default_factory=list)
    params_history: list[list[float]] = Field(
        default_factory=list,
        description=(
            r"Per-iteration free-parameter vector $\theta$ recorded alongside "
            r"each cost_history entry (same length/order). Raw material for the "
            r"convergence-to-truth metric "
            r"$d_k = \lVert (\theta_k - \theta_{\mathrm{true}})/s \rVert_2$ on synthetic "
            "cases. Empty for solvers that do not track it (only the faer LM "
            "driver records it today). Observability only."
        ),
    )
    covariance_param_order: list[str] | None = Field(
        default=None,
        description=(
            "Ordered names of the free parameters that index covariance rows/cols. "
            "covariance[i][j] is cov(covariance_param_order[i], covariance_param_order[j]). "
            "None for payloads produced before the schema added this field "
            "(backwards-compatible)."
        ),
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _validate_value_invariants(self) -> FitResult:
        r"""Boundary value guards (Invariant V, V2/V4).

        Reject only the mathematically-impossible and the structurally-inconsistent;
        deliberately tolerant of non-finite ``reduced_chi2`` / ``condition_number``
        (dof $\le$ 0 and non-estimable covariance are legitimate states — see
        [`explain`][spectrafit_core.FitResult.explain]).
        """
        # $R^2 \le 1$ always; a value above 1 is impossible. (Negative $R^2$ — worse than
        # the mean — is a legitimate poor fit and is allowed.)
        if math.isfinite(self.r_squared) and self.r_squared > 1.0 + 1e-9:
            msg = f"r_squared={self.r_squared} exceeds 1 (impossible)"
            raise ValueError(msg)
        # $\chi^2$ is a sum of squared residuals — never negative.
        if math.isfinite(self.chi2) and self.chi2 < 0.0:
            msg = f"chi2={self.chi2} is negative (impossible)"
            raise ValueError(msg)
        # The per-iteration $\theta$ trajectory is recorded lock-step with cost_history;
        # a length mismatch or ragged entry means the trajectory wire is corrupt.
        if self.params_history:
            if len(self.params_history) != len(self.cost_history):
                msg = (
                    f"params_history length {len(self.params_history)} != "
                    f"cost_history length {len(self.cost_history)} (not lock-step)"
                )
                raise ValueError(msg)
            widths = {len(theta) for theta in self.params_history}
            if len(widths) > 1:
                msg = f"params_history is ragged: differing θ lengths {sorted(widths)}"
                raise ValueError(msg)
        return self

    @property
    def params(self) -> dict[str, ParameterResult]:
        """Alias for [`parameters`][spectrafit_core.FitResult].

        Keyed by dotted parameter name mapping to its fitted result.
        """
        return self.parameters

    def explain(self) -> str:
        r"""Return a 4–6 sentence lab-notebook narrative of this fit.

        Deterministic interpretive prose synthesised from existing
        [`FitResult`][spectrafit_core.FitResult] fields — no new state, no I/O. Lines are anchored
        to numerical thresholds for ``reduced_chi2`` and ``condition_number``
        so the reader sees the "what does this number mean" verdict next to
        the value itself. Adds no fields to the model.

        The conditioning line reports $\kappa(J)$, the square root of the
        stored Gram value [`condition_number`][spectrafit_core.FitResult] $= \kappa(J^\mathsf{T}J)$,
        so its thresholds match the ones the benchmark contract uses.

        Returns:
            A multi-sentence English narrative covering convergence,
            goodness-of-fit, conditioning (when available), the dominant
            amplitude-bearing peak (when present), and AIC (when non-zero).

        """
        sentences: list[str] = []

        # ---- 1. Convergence ------------------------------------------------
        if self.success:
            sentences.append(f"Converged in {self.n_iter} iterations.")
        else:
            msg = self.message or "no message reported"
            sentences.append(
                f"Failed to converge after {self.n_iter} iterations (message: {msg}).",
            )

        # ---- 2. Goodness of fit (anchored on reduced $\chi^2$) -------------------
        rchi2 = self.reduced_chi2
        if not math.isfinite(rchi2):
            sentences.append(
                f"Reduced χ² = {rchi2} is undefined (no goodness-of-fit verdict).",
            )
        else:
            match rchi2:
                case x if x < 0.5:
                    verdict = "suggests overfitting or overestimated uncertainties"
                case x if x < 1.5:
                    verdict = "is well-scaled, indicating a good fit"
                case x if x < 3.0:
                    verdict = "indicates moderate misfit"
                case _:
                    verdict = "indicates a poor fit"
            sentences.append(f"Reduced χ² = {rchi2:.3g} {verdict}.")

        # ---- 3. Conditioning (optional) ------------------------------------
        # ``condition_number`` is the *Gram* value κ(JᵀJ) = κ(J)². Every
        # conditioning threshold in this project is stated on the κ(J) axis
        # (``oracles.bench_contract.BackendProfile``, ``oracles.backends.
        # _scipy_ls``), so square-root before comparing — mirroring
        # ``oracles.backends._spectrafit._jacobian_kappa``, which converts the
        # same field for the benchmark axis.
        gram_kappa = self.condition_number
        if gram_kappa is not None and math.isfinite(gram_kappa) and gram_kappa >= 0.0:
            kappa = math.sqrt(gram_kappa)
            match kappa:
                case k if k < 1e3:
                    cond_verdict = "well-conditioned"
                case k if k < 1e6:
                    cond_verdict = "acceptably conditioned"
                case _:
                    cond_verdict = "ill-conditioned — parameters poorly identified"
            sentences.append(f"Covariance is {cond_verdict} (κ(J) = {kappa:.3g}).")
        elif gram_kappa is not None:
            sentences.append(
                f"Covariance condition number is {gram_kappa} "
                "(non-finite or negative — covariance was not estimable).",
            )

        # ---- 4. Dominant amplitude-bearing peak (optional) -----------------
        dominant = self._dominant_amplitude_peak()
        if dominant is not None:
            amp_name, amp_pr, center_pr = dominant
            center_clause = ""
            if center_pr is not None:
                if center_pr.stderr is not None:
                    center_clause = f" at center {center_pr.value:.3g} ± {center_pr.stderr:.3g}"
                else:
                    center_clause = f" at center {center_pr.value:.3g}"
            stderr_clause = f" ± {amp_pr.stderr:.3g}" if amp_pr.stderr is not None else ""
            sentences.append(
                f"Dominant peak {amp_name} has amplitude "
                f"{amp_pr.value:.3g}{stderr_clause}{center_clause}.",
            )

        # ---- 5. Model-selection / information criterion (optional) ---------
        if self.aic != 0.0:
            sentences.append(f"AIC = {self.aic:.3g}.")

        return " ".join(sentences)

    def _dominant_amplitude_peak(
        self,
    ) -> tuple[str, ParameterResult, ParameterResult | None] | None:
        """Find the largest amplitude-bearing parameter and its center sibling.

        Scans [`parameters`][spectrafit_core.FitResult] for keys ending in ``.amplitude`` or ``.a``
        (after the dotted ``node_id.param`` convention). The one with the
        largest absolute value wins; the sibling ``<node_id>.center`` is
        returned alongside when present.

        Returns:
            ``(amplitude_key, amplitude_result, center_result_or_None)`` or
            ``None`` if no amplitude parameter exists.
        """
        amp_candidates: list[tuple[str, ParameterResult]] = []
        for key, pr in self.parameters.items():
            tail = key.rsplit(".", 1)[-1] if "." in key else key
            if tail in ("amplitude", "a"):
                amp_candidates.append((key, pr))
        if not amp_candidates:
            return None
        amp_key, amp_pr = max(amp_candidates, key=lambda kv: abs(kv[1].value))
        node_id = amp_key.rsplit(".", 1)[0] if "." in amp_key else None
        center_pr = self.parameters.get(f"{node_id}.center") if node_id else None
        return amp_key, amp_pr, center_pr
