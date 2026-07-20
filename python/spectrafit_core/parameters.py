"""Parameter and parameter-result contracts for the fitting boundary."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class Parameter(BaseModel):
    """A single fit parameter: a value, optional bounds, and constraints.

    Attributes:
        value: Initial (or fixed) parameter value.
        min: Lower bound; defaults to ``-inf``.
        max: Upper bound; defaults to ``+inf``.
        vary: Whether the solver may adjust this parameter.  Ignored when
            ``expr`` is set — the engine always derives the value from the
            expression and excludes the parameter from the free set.
        expr: Optional constraint expression referencing other parameters as
            ``node_id.param`` (e.g. ``"g1.sigma"``).  When set, the parameter
            is computed from the expression on every solver iteration and is
            excluded from the free set regardless of ``vary``.
        scale: Optional scaling hint for the solver.

    """

    value: float
    min: float = float("-inf")
    max: float = float("inf")
    vary: bool = True
    expr: str | None = None
    scale: float | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("min", mode="before")
    @classmethod
    def _null_min_to_neginf(cls, v: float | int | str | None) -> float:
        """Accept JSON null for min and convert it to -∞ (Rust serialises ±∞ as null)."""
        if v is None:
            return float("-inf")
        return float(v)

    @field_validator("max", mode="before")
    @classmethod
    def _null_max_to_posinf(cls, v: float | int | str | None) -> float:
        """Accept JSON null for max and convert it to +∞ (Rust serialises ±∞ as null)."""
        if v is None:
            return float("inf")
        return float(v)

    @model_validator(mode="after")
    def _validate_bounds(self) -> "Parameter":
        """Reject inverted bounds and an initial value outside ``[min, max]``.

        The initial-value check is enforced only for user-supplied
        :class:`Parameter` inputs; :class:`ParameterResult` (engine output) is
        exempt, since a fitted value may legitimately pin to a bound.
        """
        if self.min > self.max:
            raise ValueError(f"min ({self.min}) must not exceed max ({self.max})")
        if type(self) is Parameter and not (self.min <= self.value <= self.max):
            raise ValueError(
                f"value ({self.value}) is outside bounds [{self.min}, {self.max}]"
            )
        return self

    @model_validator(mode="after")
    def _validate_expr(self) -> "Parameter":
        """Validate that ``expr``, if set, is non-empty and not whitespace-only.

        A non-None ``expr`` that is empty or whitespace-only is meaningless and
        is rejected as a construction-time error. Users should pass ``expr=None``
        for "no expression".

        Note: ``vary`` is irrelevant when ``expr`` is set — the engine excludes
        any parameter carrying an ``expr`` from the free set, so ``vary`` has no
        effect on fitting behaviour. The field is preserved as supplied so
        callers can inspect it.
        """
        if self.expr is not None and not self.expr.strip():
            raise ValueError("expr must be a non-empty expression or None")
        return self


class ParameterResult(Parameter):
    """A fitted parameter: a :class:`Parameter` plus its name and uncertainty.

    Attributes:
        name: Dotted parameter name (``"node_id.param"``), if known.
        stderr: Estimated standard error, or ``None`` when unavailable.

    """

    name: str | None = None
    stderr: float | None = None
