"""Kafka initialization and explicit recovery metadata, never ongoing checkpoints."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, ClassVar
from uuid import UUID

from pydantic import BeforeValidator, ConfigDict, PlainSerializer, WithJsonSchema
from pydantic import Field as ValueField
from sqlalchemy import BigInteger, CheckConstraint, DateTime, text
from sqlmodel import Field, SQLModel

from syntara.eventstreams.core.consumer import MAX_POSITION_OFFSET


def _parse_offset(value: object) -> object:
    if isinstance(value, str) and value.isascii() and value.isdecimal() and (value == "0" or not value.startswith("0")):
        return int(value)
    return value


Offset = Annotated[
    int,
    ValueField(strict=True, ge=0, le=MAX_POSITION_OFFSET),
    BeforeValidator(_parse_offset),
    PlainSerializer(str, return_type=str, when_used="json"),
    WithJsonSchema({"type": "string", "pattern": "^(0|[1-9][0-9]*)$"}, mode="serialization"),
]


class GapReason(StrEnum):
    """Safe persisted explanations; no broker messages or customer payloads."""

    MISSING_COMMIT = "missing_commit"
    OUT_OF_RANGE = "out_of_range"
    BELOW_AUTHORIZED_BOUNDARY = "below_authorized_boundary"
    SOURCE_RECREATED = "source_recreated"
    INITIAL_METADATA_MISSING = "initial_metadata_missing"


class RecoveryPolicy(StrEnum):
    """The two permitted administrative gap policies, not replay controls."""

    RETAINED_BEGINNING = "retained_beginning"
    CURRENT_END = "current_end"


class PositionStatus(StrEnum):
    """Only READY permits the caller to process under the returned epoch."""

    READY = "ready"
    RECOVERY_GAP = "recovery_gap"
    BLOCKED = "blocked"
    REVISION_CHANGED = "revision_changed"
    OWNERSHIP_LOST = "ownership_lost"


class PositionValue(SQLModel):
    """Immutable service-owned values for later runners and control callers."""

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid", frozen=True)  # type: ignore[assignment]


class PositionRequest(PositionValue):
    """Expected publication and immutable source generation for one partition."""

    source_id: UUID
    source_generation: int = ValueField(gt=0, strict=True)
    configuration_revision: int = ValueField(gt=0, strict=True)
    partition: int = ValueField(ge=0, le=2**31 - 1, strict=True)
    assignment_epoch: int = ValueField(ge=0, strict=True)


class RecoveryRequest(PositionRequest):
    """Caller-authorized recovery; offsets are always selected by the service."""

    expected_recovery_revision: int = ValueField(ge=0, le=MAX_POSITION_OFFSET, strict=True)
    policy: RecoveryPolicy
    reason: str = ValueField(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_]*$")
    acknowledge_duplicate_risk: bool = ValueField(default=False, strict=True)


class RecoveryReplacementRequest(RecoveryRequest):
    """Explicitly supersede an expired pending decision, never an ordinary retry."""

    expected_pending_boundary: Offset


class PositionResult(PositionValue):
    """Durable position result; never grants ownership beyond this assignment."""

    status: PositionStatus
    next_offset: Offset | None = None
    assignment_epoch: int
    recovery_revision: int | None = None
    reason: str | None = None


class KafkaPartitionInitialPositionRead(PositionValue):
    """Lossless metadata schema for later read/control callers; no route is added."""

    source_id: UUID
    partition: int
    initial_next_offset: Offset | None
    initialized_at: datetime | None
    initial_metadata_missing: bool
    observed_group_next_offset: Offset | None
    initial_commit_confirmed_at: datetime | None
    recovery_revision: int
    recovery_boundary: Offset | None
    recovery_confirmed_at: datetime | None
    recovery_policy: RecoveryPolicy | None
    recovery_reason: str | None
    duplicate_risk_acknowledged: bool
    gap_detected_at: datetime | None
    gap_reason: GapReason | None
    pending_boundary: Offset | None
    pending_policy: RecoveryPolicy | None
    pending_reason: str | None
    pending_duplicate_risk_acknowledged: bool
    superseded_recovery_revision: int | None
    superseded_recovery_boundary: Offset | None

    @classmethod
    def from_position(cls, position: "KafkaPartitionInitialPosition") -> "KafkaPartitionInitialPositionRead":
        """Exclude the internal hold token and serialize every reading boundary losslessly."""
        return cls.model_validate(position.model_dump(exclude={"recovery_token"}))


class KafkaPartitionInitialPosition(SQLModel, table=True):
    """Keep the first boundary immutable and pending recovery fail-closed."""

    __tablename__ = "kafka_partition_initial_positions"

    source_id: UUID = Field(foreign_key="event_subscription_sources.id", ondelete="RESTRICT", primary_key=True)
    partition: int = Field(primary_key=True)
    initial_next_offset: int | None = Field(default=None, sa_type=BigInteger)
    initialized_at: datetime | None = Field(default_factory=lambda: datetime.now(UTC), sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    initial_metadata_missing: bool = Field(default=False, sa_column_kwargs={"server_default": text("false")})
    observed_group_next_offset: int | None = Field(default=None, sa_type=BigInteger)
    initial_commit_confirmed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    recovery_revision: int = Field(default=0, sa_type=BigInteger)
    recovery_boundary: int | None = Field(default=None, sa_type=BigInteger)
    recovery_confirmed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    recovery_policy: str | None = Field(default=None, max_length=32)
    recovery_reason: str | None = Field(default=None, max_length=100)
    duplicate_risk_acknowledged: bool = Field(default=False)
    gap_detected_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    gap_reason: str | None = Field(default=None, max_length=100)
    recovery_token: UUID | None = Field(
        default=None, foreign_key="event_delivery_recovery_holds.token", ondelete="RESTRICT"
    )
    pending_boundary: int | None = Field(default=None, sa_type=BigInteger)
    pending_policy: str | None = Field(default=None, max_length=32)
    pending_reason: str | None = Field(default=None, max_length=100)
    pending_duplicate_risk_acknowledged: bool = Field(default=False)
    superseded_recovery_revision: int | None = Field(default=None, sa_type=BigInteger)
    superseded_recovery_boundary: int | None = Field(default=None, sa_type=BigInteger)

    __table_args__ = (
        CheckConstraint("partition >= 0", name="ck_kafka_initial_partition"),
        CheckConstraint("initial_next_offset >= 0", name="ck_kafka_initial_offset"),
        CheckConstraint("observed_group_next_offset >= 0", name="ck_kafka_observed_group_offset"),
        CheckConstraint(
            "(NOT initial_metadata_missing AND initial_next_offset IS NOT NULL AND initialized_at IS NOT NULL "
            "AND observed_group_next_offset IS NULL) OR (initial_metadata_missing AND initial_next_offset IS NULL "
            "AND initialized_at IS NULL AND initial_commit_confirmed_at IS NULL "
            "AND observed_group_next_offset IS NOT NULL "
            "AND (gap_detected_at IS NOT NULL OR recovery_confirmed_at IS NOT NULL))",
            name="ck_kafka_initial_evidence",
        ),
        CheckConstraint("recovery_revision >= 0", name="ck_kafka_initial_revision"),
        CheckConstraint("recovery_boundary IS NULL OR recovery_boundary >= 0", name="ck_kafka_recovery_offset"),
        CheckConstraint("pending_boundary IS NULL OR pending_boundary >= 0", name="ck_kafka_pending_offset"),
        CheckConstraint(
            "(recovery_boundary IS NULL AND recovery_confirmed_at IS NULL AND recovery_policy IS NULL "
            "AND recovery_reason IS NULL) OR (recovery_boundary IS NOT NULL AND recovery_confirmed_at IS NOT NULL "
            "AND recovery_policy IN ('retained_beginning', 'current_end') AND recovery_reason IS NOT NULL)",
            name="ck_kafka_confirmed_recovery",
        ),
        CheckConstraint(
            "(recovery_token IS NULL AND pending_boundary IS NULL AND pending_policy IS NULL "
            "AND pending_reason IS NULL) OR (recovery_token IS NOT NULL AND pending_policy "
            "IN ('retained_beginning', 'current_end') AND pending_reason IS NOT NULL AND gap_detected_at IS NOT NULL)",
            name="ck_kafka_pending_recovery",
        ),
        CheckConstraint("(gap_detected_at IS NULL) = (gap_reason IS NULL)", name="ck_kafka_gap_evidence"),
        CheckConstraint(
            "(superseded_recovery_revision IS NULL AND superseded_recovery_boundary IS NULL) OR "
            "(superseded_recovery_revision IS NOT NULL AND superseded_recovery_revision >= 0 "
            "AND superseded_recovery_revision < recovery_revision AND superseded_recovery_boundary IS NOT NULL "
            "AND superseded_recovery_boundary >= 0)",
            name="ck_kafka_superseded_recovery",
        ),
    )

    @property
    def authorized_lower_boundary(self) -> int | None:
        """Confirmed recovery can explicitly authorize a boundary before initialization."""
        return self.initial_next_offset if self.recovery_boundary is None else self.recovery_boundary
