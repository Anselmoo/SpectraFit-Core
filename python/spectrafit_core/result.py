"""Fit-result contracts: fitted parameters, diagnostics, and per-slice data."""

from __future__ import annotations

import math

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from .parameters import ParameterResult


class DatasetSlice(BaseModel):
    """Per-dataset diagnostics for multi-dataset global fits.

    Attributes:
        label: Optional human-readable label for this slice (may be ``None``).
        n_points: Number of data points in this slice.
        best_fit: Model values at the fitted parameters, length ``n_points``.
        residuals: Signed residuals ``(y_observed − y_fit)``, length ``n_points``.
        chi2: Sum of squared residuals for this slice only.

    """

    label: str | None = None
    n_points: int
    best_fit: list[float]
    residuals: list[float]
    chi2: float

    model_config = ConfigDict(extra="forbid")


class FitResult(BaseModel):
    """Result of a single :func:`~spectrafit_core.fit` call.

    Attributes:
        schema_version: IR schema version of the producing engine.
        parameters: Fitted parameter values and uncertainties, keyed by
            ``"node_id.param_name"`` (dotted notation).
        covariance: Parameter covariance matrix (row/column order matches
            ``parameters``), or ``None`` if the solver could not estimate it.
        chi2: Total sum of squared (weighted) residuals.
        reduced_chi2: ``chi2 / dof`` — values near 1.0 indicate a good fit.
        r_squared: Coefficient of determination R².
        dof: Degrees of freedom (``n_data − n_free_params``).
        aic: Akaike Information Criterion.
        bic: Bayesian Information Criterion.
        n_iter: Number of solver iterations taken.
        n_func_evals: Number of residual evaluations (``None`` if unavailable).
        n_jac_evals: Number of Jacobian evaluations (``None`` if unavailable).
        success: ``True`` if the solver converged within ``max_iterations``.
        message: Human-readable solver status message.
        best_fit: Model values at the fitted parameters, one per data point.
        residuals: Signed residuals ``(y_observed − y_fit)``.
        init_fit: Model values evaluated at the initial-guess parameters.
        components: Per-node contributions summing to ``best_fit``.
        dataset_slices: Per-dataset diagnostics for multi-dataset fits,
            ``None`` for single-dataset fits.
        condition_number: Condition number of ``JᵀJ`` at the solution (ratio of
            largest to smallest singular value). Large values flag an
            ill-conditioned, poorly determined fit. ``None`` when the solver did
            not compute it.
        n_de_generations: Number of differential-evolution generations run before
            the LM refinement on the ``solver="global"`` path. ``None`` for
            direct LM and other solvers. Makes the DE search effort visible, since
            ``n_iter`` counts only the post-DE refinement (often 0).
        cost_history: Per-iteration cost ``½‖r‖²`` trajectory from the faer LM /
            trust-region drivers (index 0 = initial point, last = terminal cost).
            Empty for solvers that do not track it (``solver="lm-legacy"`` /
            ``"varpro"``). Observability only — it does not affect the fit.
        gradient_norm_history: Per-iteration gradient infinity-norm ``‖Jᵀr‖_∞``
            recorded alongside each :attr:`cost_history` entry. Empty when not tracked.
        covariance_param_order: Ordered list of free-parameter names that index the
            rows and columns of :attr:`covariance`. ``covariance[i][j]`` is the
            covariance between ``covariance_param_order[i]`` and
            ``covariance_param_order[j]``.  Use this to look up cross-terms by name
            rather than relying on :attr:`parameters` iteration order (which is
            non-deterministic for ``HashMap``-backed dicts).  ``None`` for payloads
            produced before Cycle 21 (backwards-compatible default).

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
            "Per-iteration free-parameter vector θ recorded alongside each "
            "cost_history entry (same length/order). Raw material for the "
            "convergence-to-truth metric dₖ = ‖(θₖ − θ_true)/s‖₂ on synthetic "
            "cases. Empty for solvers that do not track it (only the faer LM "
            "driver records it today). Observability only."
        ),
    )
    covariance_param_order: list[str] | None = Field(
        default=None,
        description=(
            "Ordered names of the free parameters that index covariance rows/cols. "
            "covariance[i][j] is cov(covariance_param_order[i], covariance_param_order[j]). "
            "None for payloads produced before Cycle 21 (backwards-compatible)."
        ),
    )

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    @model_validator(mode="after")
    def _validate_value_invariants(self) -> "FitResult":
        """Boundary value guards (Invariant V, V2/V4).

        Reject only the mathematically-impossible and the structurally-inconsistent;
        deliberately tolerant of non-finite ``reduced_chi2`` / ``condition_number``
        (dof ≤ 0 and non-estimable covariance are legitimate states — see
        :meth:`explain`).
        """
        # R² ≤ 1 always; a value above 1 is impossible. (Negative R² — worse than
        # the mean — is a legitimate poor fit and is allowed.)
        if math.isfinite(self.r_squared) and self.r_squared > 1.0 + 1e-9:
            raise ValueError(f"r_squared={self.r_squared} exceeds 1 (impossible)")
        # χ² is a sum of squared residuals — never negative.
        if math.isfinite(self.chi2) and self.chi2 < 0.0:
            raise ValueError(f"chi2={self.chi2} is negative (impossible)")
        # The per-iteration θ trajectory is recorded lock-step with cost_history;
        # a length mismatch or ragged entry means the trajectory wire is corrupt.
        if self.params_history:
            if len(self.params_history) != len(self.cost_history):
                raise ValueError(
                    f"params_history length {len(self.params_history)} != "
                    f"cost_history length {len(self.cost_history)} (not lock-step)"
                )
            widths = {len(theta) for theta in self.params_history}
            if len(widths) > 1:
                raise ValueError(
                    f"params_history is ragged: differing θ lengths {sorted(widths)}"
                )
        return self

    @property
    def params(self) -> dict[str, ParameterResult]:
        """Alias for :attr:`parameters` (dotted-name → fitted result)."""
        return self.parameters

    def explain(self) -> str:
        """Return a 4–6 sentence lab-notebook narrative of this fit.

        Deterministic interpretive prose synthesised from existing
        :class:`FitResult` fields — no new state, no I/O. Lines are anchored
        to numerical thresholds for ``reduced_chi2`` and ``condition_number``
        so the reader sees the "what does this number mean" verdict next to
        the value itself. Adds no fields to the model.

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
                f"Failed to converge after {self.n_iter} iterations (message: {msg})."
            )

        # ---- 2. Goodness of fit (anchored on reduced χ²) -------------------
        rchi2 = self.reduced_chi2
        if not math.isfinite(rchi2):
            sentences.append(
                f"Reduced χ² = {rchi2} is undefined (no goodness-of-fit verdict)."
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
        kappa = self.condition_number
        if kappa is not None and math.isfinite(kappa):
            match kappa:
                case k if k < 1e3:
                    cond_verdict = "well-conditioned"
                case k if k < 1e6:
                    cond_verdict = "acceptably conditioned"
                case _:
                    cond_verdict = "ill-conditioned — parameters poorly identified"
            sentences.append(f"Covariance is {cond_verdict} (κ = {kappa:.3g}).")
        elif kappa is not None:
            sentences.append(
                f"Covariance condition number is {kappa} "
                "(non-finite — covariance was not estimable)."
            )

        # ---- 4. Dominant amplitude-bearing peak (optional) -----------------
        dominant = self._dominant_amplitude_peak()
        if dominant is not None:
            amp_name, amp_pr, center_pr = dominant
            center_clause = ""
            if center_pr is not None:
                if center_pr.stderr is not None:
                    center_clause = (
                        f" at center {center_pr.value:.3g} ± {center_pr.stderr:.3g}"
                    )
                else:
                    center_clause = f" at center {center_pr.value:.3g}"
            stderr_clause = (
                f" ± {amp_pr.stderr:.3g}" if amp_pr.stderr is not None else ""
            )
            sentences.append(
                f"Dominant peak {amp_name} has amplitude "
                f"{amp_pr.value:.3g}{stderr_clause}{center_clause}."
            )

        # ---- 5. Model-selection / information criterion (optional) ---------
        if self.aic != 0.0:
            sentences.append(f"AIC = {self.aic:.3g}.")

        return " ".join(sentences)

    def _dominant_amplitude_peak(
        self,
    ) -> tuple[str, ParameterResult, ParameterResult | None] | None:
        """Find the largest amplitude-bearing parameter and its center sibling.

        Scans :attr:`parameters` for keys ending in ``.amplitude`` or ``.a``
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
