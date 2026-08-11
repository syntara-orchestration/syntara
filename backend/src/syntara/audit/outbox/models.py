"""Audit outbox and metadata models for transactional event capture."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar
from uuid import UUID, uuid4

from sqlalchemy import Index, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlmodel import Column, DateTime, Field, SQLModel

from syntara.core.models.base.base_resource import AuditLevel
from syntara.core.utils.sqlmodel import postgres_enum_column


def _utc_now() -> datetime:
    """Generate UTC timestamp for field defaults."""
    return datetime.now(UTC)


class AuditEventSource(StrEnum):
    """Source type for audit events in the outbox.

    Both event sources are routed to the OTEL Collector. The distinction
    is retained for filtering and observability (the ``audit.event_source``
    attribute on exported spans/logs).

    Values are in alphabetical order to ensure PostgreSQL sorts them correctly
    (PostgreSQL enums sort by definition order, not by value).
    """

    BUSINESS_EVENT = "business_event"
    CRUD_EVENT = "crud_event"


class AuditOutboxRecord(SQLModel, table=True):
    """Transactional outbox for audit events.

    Stores audit events in the main database within the same transaction as
    business data changes. A background worker polls this table, publishes
    records to the audit database, then deletes them.

    This guarantees at-least-once delivery - if the process crashes after
    commit but before audit write, the background worker will retry on restart.

    Records are temporary and deleted immediately after successful publication
    to prevent unbounded growth.
    """

    __tablename__ = "audit_outbox"

    # Disable CRUD auditing to prevent recursion (outbox shouldn't audit itself)
    __auditable__: ClassVar[AuditLevel] = AuditLevel.NONE

    # Primary key
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="Unique identifier for the outbox record",
    )

    # Creation timestamp for FIFO processing
    created_at: datetime = Field(
        default_factory=_utc_now,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        sa_column_kwargs={"server_default": text("now()")},
        description="When the event was captured",
    )

    # Event source for routing decisions
    event_source: AuditEventSource = Field(
        default=AuditEventSource.BUSINESS_EVENT,
        sa_column=postgres_enum_column(
            AuditEventSource,
            "auditeventsource",
            server_default=text("'business_event'::auditeventsource"),
        ),
        description="Source type for filtering (both routed to OTEL Collector)",
    )

    # Number of OTEL export attempts (incremented on each failure)
    dispatch_attempts: int = Field(
        default=0,
        sa_column_kwargs={"server_default": text("0")},
        description="Number of failed OTEL export attempts for this record",
    )

    # Serialized event payload (AuditEvent as JSON)
    event_payload: dict[str, Any] = Field(
        sa_type=JSONB,
        description="Serialized AuditEvent ready for dispatch",
    )

    # Index for efficient worker queries (oldest first for FIFO processing)
    __table_args__ = (Index("ix_audit_outbox_created_at", "created_at"),)


class AuditTableMetadata(SQLModel, table=True):
    """Metadata table for audit trigger configuration.

    Stores audit configuration for each table, allowing the generic trigger
    function to determine if a table should be audited and which fields to capture.

    Populated during migration by introspecting Python models for __auditable__
    and __auditable_fields__ settings.
    """

    __tablename__ = "audit_table_metadata"

    # Disable CRUD auditing to prevent recursion (metadata table shouldn't audit itself)
    __auditable__: ClassVar[AuditLevel] = AuditLevel.NONE

    # Table name (primary key)
    table_name: str = Field(
        primary_key=True,
        description="Database table name (e.g., 'user', 'workflow_version')",
    )

    # Python model name
    model_name: str = Field(
        description="Python model class name (e.g., 'User', 'WorkflowVersion')",
    )

    # Audit level (FULL or META)
    audit_level: str = Field(
        description="Audit granularity: 'full' captures all fields, 'meta' captures only metadata fields",
    )

    # Auditable fields (NULL for FULL, array for META)
    auditable_fields: list[str] | None = Field(
        default=None,
        sa_column=Column(ARRAY(Text), nullable=True),
        description="Fields to audit in META mode (NULL for FULL mode = all fields)",
    )
