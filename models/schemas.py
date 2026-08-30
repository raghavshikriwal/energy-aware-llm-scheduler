"""Pydantic request schemas for the API layer.

Moving validation here (instead of hand-rolled `isinstance`/`all()` checks
inline in the route) makes the schema itself the single source of truth for
what a valid request looks like, gives consistent, structured error
messages for free, and keeps `routes/api.py` focused on orchestration
rather than input-shape policing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


class GPUFleetConfig(BaseModel):
    """Optional custom GPU fleet parameters sent in a /api/compare or
    /api/sensitivity POST body.

    All fields are optional — an empty or missing body falls back to the
    module defaults in `services/round_robin_scheduler.py`, so existing
    callers that send nothing keep working unchanged.
    """

    efficiency_factors: list[float] | None = Field(
        default=None,
        description="Power-efficiency multiplier per GPU class. Must be positive.",
    )
    compute_capabilities: list[float] | None = Field(
        default=None,
        description="Relative throughput multiplier per GPU class. Must be positive.",
    )
    num_gpus: int | None = Field(
        default=None,
        gt=0,
        le=64,
        description="Number of GPUs to simulate. Defaults to len(efficiency_factors).",
    )

    @field_validator("efficiency_factors", "compute_capabilities")
    @classmethod
    def _all_positive(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        if not value:
            raise ValueError("list must not be empty")
        if any(x <= 0 for x in value):
            raise ValueError("all values must be positive numbers")
        return value

    @model_validator(mode="after")
    def _matching_lengths(self) -> "GPUFleetConfig":
        if (
            self.efficiency_factors is not None
            and self.compute_capabilities is not None
            and len(self.efficiency_factors) != len(self.compute_capabilities)
        ):
            raise ValueError(
                "efficiency_factors and compute_capabilities must be the same length"
            )
        return self