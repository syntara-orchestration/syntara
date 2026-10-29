"""Strict operational inputs: no connection settings, secrets, identity or offsets."""

from typing import ClassVar, Literal
from uuid import UUID

from pydantic import ConfigDict
from pydantic import Field as ValueField
from sqlmodel import SQLModel

from syntara.eventstreams.adapters.kafka_initial_position import RecoveryPolicy
from syntara.eventstreams.core.runtime import RuntimeState


class SubscriptionControlRequest(SQLModel):
    """Compare-and-set against the published projection and source generation."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    configuration_revision: int = ValueField(gt=0, le=2**63 - 1, strict=True)
    source_generation: int = ValueField(gt=0, le=2**31 - 1, strict=True)


class SubscriptionRecoveryRequest(SubscriptionControlRequest):
    """Boundary policy only; the assigned worker resolves the effective offset."""

    partition: int = ValueField(ge=0, le=2**31 - 1, strict=True)
    expected_recovery_revision: int = ValueField(ge=0, le=2**63 - 1, strict=True)
    policy: RecoveryPolicy
    reason: str = ValueField(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    acknowledge_duplicate_risk: bool = ValueField(default=False, strict=True)
    resolve_unscheduled: bool = ValueField(default=False, strict=True)


class SubscriptionRetireRequest(SubscriptionControlRequest):
    """Safe retirement by default; disposition requires its separate grant."""

    resolve_unscheduled: bool = ValueField(default=False, strict=True)
    reason: str = ValueField(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")


class SubscriptionControlResponse(SQLModel):
    """A committed action; pending is not proof that every consumer has stopped."""

    subscription_id: UUID
    source_id: UUID
    configuration_revision: int
    source_generation: int
    convergence: Literal["pending", "applied"]
    applied_revision: int | None = None
    runtime_state: RuntimeState | None = None
