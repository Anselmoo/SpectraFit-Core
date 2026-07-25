"""Model-node specifications and the supported model-type enumeration."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

from .parameters import Parameter


class ModelType(StrEnum):
    """Supported model kernels, identified by their canonical string name."""

    GAUSSIAN = "gaussian"
    GAUSSIAN2D = "gaussian2d"
    GAUSSIAN_ND = "gaussian_nd"
    LORENTZIAN = "lorentzian"
    VOIGT = "voigt"
    CONSTANT = "constant"
    LINEAR = "linear"
    QUADRATIC = "quadratic"
    ARCTAN_STEP = "arctan_step"
    TANH_STEP = "tanh_step"
    ERFC_STEP = "erfc_step"
    PSEUDO_VOIGT = "pseudo_voigt"
    FANO = "fano"
    DOUBLE_EXPONENTIAL = "double_exponential"
    TRUE_VOIGT = "true_voigt"
    SKEWED_GAUSSIAN = "skewed_gaussian"
    EXP_GAUSSIAN = "exp_gaussian"
    DONIACH = "doniach_sunjic"
    LOG_NORMAL = "log_normal"
    PEARSON7 = "pearson7"
    SPLIT_GAUSSIAN = "split_gaussian"
    MOFFAT = "moffat"
    STUDENTS_T = "students_t"
    SPLIT_PEARSON7 = "split_pearson7"
    BREIT_WIGNER = "breit_wigner"
    ASYM_IR = "asym_ir"
    HARMONIC_IR = "harmonic_ir"
    TAUC = "tauc"
    CAUCHY_DISPERSION = "cauchy_dispersion"
    KWW = "kww"
    SATURATING_EXPONENTIAL = "saturating_exponential"
    POWER_SATURATION = "power_saturation"
    POWER_LAW_OFFSET = "power_law_offset"
    MGH09_RATIONAL = "mgh09_rational"

    @classmethod
    def _missing_(cls, value: object) -> "ModelType | None":
        if isinstance(value, str):
            lowered = value.lower()
            for member in cls:
                if member.value == lowered:
                    return member
        return None


class ModelNodeSpec(BaseModel):
    """One model node: a unique ``id``, a ``model_type``, and its parameters.

    Attributes:
        id: Unique node identifier within a graph.
        model_type: Which model kernel this node evaluates.
        parameters: Parameter definitions keyed by parameter name.
        dataset_index: Dataset scope for simultaneous multi-dataset ("global
            analysis") fits. ``None`` (default) = global node, contributing to
            every dataset's points. ``i`` = local to dataset ``i``, contributing
            residuals/Jacobian only to that dataset's contiguous point-range.

    """

    id: str
    model_type: ModelType
    parameters: dict[str, Parameter]
    dataset_index: int | None = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("dataset_index")
    @classmethod
    def _dataset_index_non_negative(cls, v: int | None) -> int | None:
        """Reject a negative dataset_index before it reaches the Rust wire boundary.

        The Rust side deserializes this field as ``Option<usize>``
        (crates/spectrafit-types/src/types.rs), which cannot represent a
        negative value — a negative index must fail fast in Python, not at
        the FFI deserialization boundary.
        """
        if v is not None and v < 0:
            msg = f"dataset_index must be non-negative, got {v}"
            raise ValueError(msg)
        return v
