"""Durable transport-neutral delivery coordination, without payload storage."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Index, text
from sqlmodel import Field, SQLModel

from syntara.core.utils.sqlmodel import DiscriminatedJSONB
from syntara.eventstreams.adapters.delivery_indexes import all_delivery_record_indexes
from syntara.eventstreams.adapters.record_identity import RecordIdentity, RecordIdentityTypes
from syntara.eventstreams.core.deduplication import DeliveryIdentity, FrozenDeliveryBinding


class EventDelivery(SQLModel, table=True):
    """Retain identity/outcomes independently of ordinary Execution cascades."""

    __tablename__ = "event_deliveries"

    identity_digest: str = Field(primary_key=True, max_length=64)
    identity_version: int = Field(default=1)
    deployment_id: UUID
    integration_identity: UUID
    source_id: UUID = Field(foreign_key="event_subscription_sources.id", ondelete="RESTRICT")
    source_generation: int
    transport: str = Field(max_length=32)
    workflow_id: UUID
    subscription_id: UUID
    record_identity: RecordIdentityTypes = Field(
        sa_type=DiscriminatedJSONB(RecordIdentity),  # type: ignore[call-overload]
    )

    state: str = Field(default="in_progress", max_length=32)
    claim_token: UUID | None = None
    owner_worker_id: str | None = Field(default=None, max_length=255)
    lease_until: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    frozen_binding: FrozenDeliveryBinding | None = Field(
        default=None,
        sa_type=DiscriminatedJSONB(FrozenDeliveryBinding),  # type: ignore[call-overload]
    )

    # The value survives SET NULL of the historical FK. The CHECK below prevents
    # SET NULL from deleting the frozen Execution of unresolved prepared work.
    execution_identity: UUID = Field(unique=True)
    execution_id: UUID | None = Field(default=None, foreign_key="executions.id", ondelete="SET NULL")
    temporal_workflow_id: str = Field(max_length=255, unique=True)
    temporal_run_id: str | None = Field(default=None, max_length=255)
    execution_confirmed_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]

    attempt_count: int = Field(default=0, sa_type=BigInteger)
    first_start_attempt_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    start_retry_deadline: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    scheduling_failure_count: int = Field(default=0, sa_type=BigInteger, sa_column_kwargs={"server_default": text("0")})
    next_attempt_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": text("clock_timestamp()")},
    )
    last_error_code: str | None = Field(default=None, max_length=100)
    resolved_at: datetime | None = Field(default=None, sa_type=DateTime(timezone=True))  # type: ignore[call-overload]
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": text("clock_timestamp()")},
    )

    __table_args__ = (
        CheckConstraint("identity_version = 1", name="ck_event_deliveries_identity_version"),
        CheckConstraint("source_generation > 0", name="ck_event_deliveries_generation"),
        CheckConstraint("attempt_count >= 0", name="ck_event_deliveries_attempt_count"),
        CheckConstraint("scheduling_failure_count >= 0", name="ck_event_deliveries_scheduling_failure_count"),
        CheckConstraint(
            "start_retry_deadline IS NULL OR (first_start_attempt_at IS NOT NULL "
            "AND start_retry_deadline > first_start_attempt_at)",
            name="ck_event_deliveries_start_retry_deadline",
        ),
        CheckConstraint(
            "state IN ('in_progress', 'scheduled', 'filtered', 'rejected', 'cancelled')",
            name="ck_event_deliveries_state",
        ),
        CheckConstraint(
            "(state = 'in_progress' AND resolved_at IS NULL) OR (state <> 'in_progress' AND resolved_at IS NOT NULL)",
            name="ck_event_deliveries_resolution",
        ),
        CheckConstraint(
            "(claim_token IS NULL AND owner_worker_id IS NULL AND lease_until IS NULL) OR "
            "(claim_token IS NOT NULL AND owner_worker_id IS NOT NULL AND lease_until IS NOT NULL)",
            name="ck_event_deliveries_claim",
        ),
        CheckConstraint(
            "state <> 'scheduled' OR (frozen_binding IS NOT NULL AND temporal_run_id IS NOT NULL "
            "AND execution_confirmed_at IS NOT NULL)",
            name="ck_event_deliveries_scheduled_evidence",
        ),
        CheckConstraint(
            "state <> 'in_progress' OR frozen_binding IS NULL OR execution_id IS NOT NULL",
            name="ck_event_deliveries_unresolved_execution",
        ),
        CheckConstraint(
            "execution_id IS NULL OR execution_id = execution_identity",
            name="ck_event_deliveries_execution_identity",
        ),
        CheckConstraint(
            "(attempt_count = 0 AND first_start_attempt_at IS NULL) OR "
            "(attempt_count > 0 AND first_start_attempt_at IS NOT NULL AND frozen_binding IS NOT NULL)",
            name="ck_event_deliveries_start_attempt",
        ),
        Index(
            "ix_event_deliveries_due",
            "next_attempt_at",
            "lease_until",
            "identity_digest",
            postgresql_where=text("state = 'in_progress'"),
        ),
        Index(
            "ix_event_deliveries_unowned_due",
            "next_attempt_at",
            "identity_digest",
            postgresql_where=text("state = 'in_progress' AND claim_token IS NULL"),
        ),
        Index(
            "ix_event_deliveries_terminal_cleanup",
            "source_id",
            "resolved_at",
            "identity_digest",
            postgresql_where=text("state <> 'in_progress'"),
        ),
        *all_delivery_record_indexes(),
    )

    def delivery_identity(self) -> DeliveryIdentity:
        """Rebuild and verify retained canonical coordinates before returning evidence."""
        identity = DeliveryIdentity(
            identity_version=self.identity_version,
            deployment_id=self.deployment_id,
            integration_identity=self.integration_identity,
            source_id=self.source_id,
            source_generation=self.source_generation,
            workflow_id=self.workflow_id,
            subscription_id=self.subscription_id,
            record=self.record_identity,
        )
        if (
            identity.digest != self.identity_digest
            or identity.execution_id != self.execution_identity
            or identity.temporal_workflow_id != self.temporal_workflow_id
        ):
            msg = "Stored delivery identity does not match its canonical coordinates"
            raise ValueError(msg)
        return identity
