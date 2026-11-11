"""EventSubscriptionSource SQLModel: per-generation source identity and lifecycle.

An ``EventSubscriptionSource`` preserves one source generation of an
``EventSubscription``: the transport, the integration/source identity it binds
to, its typed transport-specific configuration, and its creation/retirement
boundary. Replacing a source (for example a changed topic or integration)
creates a new generation and retires the prior one; retirement never deletes the
row, so downstream recovery can still discover it.

The table is transport-neutral. Kafka-specific addressing lives in the typed
``configuration`` JSONB (see the adapters layer); other transports add their own
configuration variant without gaining columns here.
"""

from datetime import datetime
from typing import ClassVar
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, Index, text
from sqlmodel import Field

from syntara.core.models.base import BaseResource
from syntara.core.utils.sqlmodel import DiscriminatedJSONB
from syntara.eventstreams.adapters.source_configuration import (
    SourceConfiguration,
    SourceConfigurationTypes,
)

_TRANSPORT_MAX_LENGTH = 32
_CONFIGURATION_DESCRIPTION = "Typed transport-specific source address; no secrets or event payloads"


class EventSubscriptionSource(BaseResource, table=True):
    """One source generation retained for its subscription's recovery window.

    Inherits ``id``, ``created_at``, ``updated_at`` and ``labels`` from
    ``BaseResource``. A source is created inside the workflow publication
    transaction and is immutable apart from its initialization/retirement
    boundary fields.
    """

    __tablename__ = "event_subscription_sources"

    __filterable_fields__: ClassVar[list[str]] = [
        *BaseResource.__filterable_fields__,
        "subscription_id",
        "integration_id",
        "transport",
        "generation",
    ]

    __sortable_fields__: ClassVar[list[str]] = [
        *BaseResource.__sortable_fields__,
        "generation",
    ]

    subscription_id: UUID = Field(
        foreign_key="event_subscriptions.id",
        ondelete="CASCADE",
        index=True,
        description="FK to the owning subscription; sources are retained children of a subscription",
    )

    deployment_id: UUID = Field(
        description="Persisted deployment namespace (Installation.id); never generated per worker",
    )

    generation: int = Field(
        description="Source generation, unique per subscription; positive and monotonically allocated",
    )

    integration_id: UUID | None = Field(
        default=None,
        foreign_key="integrations.id",
        ondelete="RESTRICT",
        index=True,
        description="FK to the bound Integration; required for an active source",
    )

    integration_identity: UUID = Field(
        description="Immutable canonical Integration identity, retained even if the Integration is deleted",
    )

    transport: str = Field(
        max_length=_TRANSPORT_MAX_LENGTH,
        index=True,
        description="Transport discriminator matching the typed configuration; currently 'kafka'",
    )

    configuration: SourceConfigurationTypes = Field(
        sa_type=DiscriminatedJSONB(SourceConfiguration),  # type: ignore[call-overload]
        description=_CONFIGURATION_DESCRIPTION,
    )

    initialized_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="When this source was first verified/initialized; distinct from retirement",
    )

    retired_at: datetime | None = Field(
        default=None,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="When this source was retired; retirement never deletes the row",
    )

    __table_args__ = (
        CheckConstraint("generation > 0", name="ck_event_subscription_sources_generation_positive"),
        # NOTE: When adding a new transport, also update this check in a migration.
        CheckConstraint(
            "transport IN ('kafka')",
            name="ck_event_subscription_sources_transport_valid",
        ),
        # One generation number per subscription.
        Index(
            "ix_event_subscription_sources_subscription_generation",
            "subscription_id",
            "generation",
            unique=True,
        ),
        # Kafka-only partial-unique index over the generated consumer group id
        # (a JSONB expression). A replaced source gets a new generation and group,
        # so group ids stay unique within Kafka sources.
        Index(
            "ix_event_subscription_sources_kafka_group_id",
            text("(configuration->>'group_id')"),
            unique=True,
            postgresql_where=text("transport = 'kafka'"),
        ),
        Index(
            "ix_event_subscription_sources_labels",
            "labels",
            postgresql_using="gin",
        ),
    )
