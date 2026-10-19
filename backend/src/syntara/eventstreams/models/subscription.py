"""EventSubscription SQLModel: the operational projection of a published trigger.

An ``EventSubscription`` is the transport-neutral, derived operational state of a
stable workflow trigger node. It is projected from the published workflow
definition inside the publication transaction. It is not a ``NamedResource`` —
the workflow and trigger node supply its name — and it retains the last applied
published configuration even while unpublished so republish preserves identity,
group and reading progress.

Each subscription owns one or more ``EventSubscriptionSource`` generations; the
``active_source_generation`` points at the current one while enabled. Kafka
topics, groups and offsets live on the source configuration and adapter-specific
state, never on this table.
"""

from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field

from syntara.core.models.base.user_owned import UserOwnedResource

_TRIGGER_NODE_ID_MAX_LENGTH = 255


class EventSubscription(UserOwnedResource, table=True):
    """One logical subscription per workflow trigger; retired rows may coexist.

    Inherits ``id``, ``created_at``, ``updated_at``, ``labels`` from
    ``BaseResource`` and ``created_by``/``updated_by`` principal references from
    ``UserOwnedResource``. The effective desire is published, not paused and not
    retired.
    """

    __tablename__ = "event_subscriptions"

    __filterable_fields__: ClassVar[list[str]] = [
        *UserOwnedResource.__filterable_fields__,
        "workflow_id",
        "project_id",
        "trigger_node_id",
        "desired_enabled",
        "paused",
        "retired",
    ]

    __sortable_fields__: ClassVar[list[str]] = [
        *UserOwnedResource.__sortable_fields__,
        "configuration_revision",
    ]

    workflow_id: UUID = Field(
        foreign_key="workflows.id",
        ondelete="RESTRICT",
        index=True,
        description="FK to the owning workflow; RESTRICT so deletion cannot erase bound evidence",
    )

    project_id: UUID = Field(
        foreign_key="projects.id",
        index=True,
        description="Project namespace, denormalized for scoped queries",
    )

    trigger_node_id: str = Field(
        max_length=_TRIGGER_NODE_ID_MAX_LENGTH,
        description="Trigger node ID in the workflow definition; unique per workflow among non-retired rows",
    )

    published_version_id: UUID = Field(
        foreign_key="workflow_versions.id",
        ondelete="RESTRICT",
        index=True,
        description="Last applied published configuration; retained while unpublished",
    )

    active_source_generation: int = Field(
        description="Positive; identifies the current source generation when enabled",
    )

    configuration_revision: int = Field(
        sa_type=BigInteger,
        description="Positive, monotonic; advances on published configuration change or pause/resume",
    )

    runtime_credential_id: UUID | None = Field(
        default=None,
        foreign_key="credentials.id",
        ondelete="RESTRICT",
        index=True,
        description="Runtime credential reference; required combinations validated by the transport",
    )

    input_schema: dict[str, Any] | None = Field(
        default=None,
        sa_type=JSONB,
        description="Validated published input schema; filter configuration/schema is out of scope",
    )

    desired_enabled: bool = Field(
        default=True,
        description="Whether a published version desires consumption",
    )

    paused: bool = Field(
        default=False,
        description="User-controlled operational pause; does not rewrite the workflow version",
    )

    retired: bool = Field(
        default=False,
        description="Terminal retirement; retired rows remain discoverable for recovery",
    )

    enabled_by: UUID | None = Field(
        default=None,
        foreign_key="principals.id",
        description="Actor that last authorized activation; snapshotted into firing metadata",
    )

    __table_args__ = (
        CheckConstraint(
            "active_source_generation > 0",
            name="ck_event_subscriptions_active_generation_positive",
        ),
        CheckConstraint(
            "configuration_revision > 0",
            name="ck_event_subscriptions_configuration_revision_positive",
        ),
        # One live logical subscription per workflow trigger; retired rows may coexist.
        Index(
            "ix_event_subscriptions_workflow_trigger_active",
            "workflow_id",
            "trigger_node_id",
            unique=True,
            postgresql_where=text("retired = false"),
        ),
        # Desired-state scan for downstream reconciliation.
        Index(
            "ix_event_subscriptions_desired_scan",
            "desired_enabled",
            "retired",
            "id",
        ),
        # Project/workflow scoped lookup.
        Index(
            "ix_event_subscriptions_project_workflow",
            "project_id",
            "workflow_id",
        ),
        Index(
            "ix_event_subscriptions_labels",
            "labels",
            postgresql_using="gin",
        ),
    )
