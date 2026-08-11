"""WebhookTrigger SQLModel for webhook trigger registration and lookup.

This module provides the WebhookTrigger table model for the operational lookup table
that maps webhook paths to workflows and stores JSON schemas for payload validation.

The table supports multiple trigger types (webhook_trigger, eda_trigger) via the
``trigger_type`` discriminator column. Uniqueness is scoped per type — the same
webhook_path can exist for both a webhook trigger and an EDA trigger because they
live under different URL namespaces (``/webhooks/{path}`` vs ``/webhooks/eda/{path}``).

The webhook trigger configuration (webhook_path, input_schema) is the source of truth
in the workflow definition JSONB. This table is a derived index for fast lookup and
stores operational data (enabled state) not present in the definition.
"""

from datetime import datetime
from typing import Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import CheckConstraint, Field, Index, SQLModel

from syntara.core.constants import WebhookLimits
from syntara.core.models.base import BaseResource
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType


class WebhookTrigger(BaseResource, table=True):
    """Webhook trigger lookup table for routing incoming webhooks to workflows.

    This table is auto-synced from workflow definitions. When a workflow contains
    a webhook_trigger node, a corresponding row is created/updated here. The row
    is deleted when the workflow is deleted or the trigger node is removed.

    Attributes:
        id: Primary key UUID (from BaseResource)
        trigger_type: Discriminator — "webhook_trigger" or "eda_trigger"
        webhook_path: URL slug for the webhook endpoint (unique per trigger_type)
        workflow_id: FK to the workflow that owns this trigger
        trigger_node_id: The node ID within the workflow definition
        input_schema: Optional JSON Schema (Draft-07) for payload validation
        is_enabled: Whether this webhook trigger is active
        created_at: Timestamp of creation (from BaseResource)
        updated_at: Timestamp of last update (from BaseResource)

    """

    __tablename__ = "webhook_triggers"

    __filterable_fields__: ClassVar[list[str]] = [
        *BaseResource.__filterable_fields__,
        "trigger_type",
        "webhook_path",
        "workflow_id",
        "is_enabled",
    ]

    __sortable_fields__: ClassVar[list[str]] = [
        *BaseResource.__sortable_fields__,
    ]

    # Trigger type discriminator
    trigger_type: str = Field(
        default=NodeType.WEBHOOK_TRIGGER,
        max_length=50,
        description="Trigger type: 'webhook_trigger' or 'eda_trigger'",
        index=True,
    )

    # Webhook endpoint configuration
    webhook_path: str = Field(
        max_length=WebhookLimits.PATH_MAX_LENGTH,
        description="URL slug for the webhook endpoint (unique per trigger_type)",
    )

    # Workflow association
    workflow_id: UUID = Field(
        foreign_key="workflows.id",
        ondelete="CASCADE",
        description="FK to the workflow that owns this trigger",
        index=True,
    )

    trigger_node_id: str = Field(
        max_length=255,
        description="The node ID within the workflow definition",
    )

    # Optional payload validation schema
    input_schema: dict[str, Any] | None = Field(
        default=None,
        sa_type=JSONB,
        description="Optional JSON Schema (Draft-07) for payload validation",
    )

    # Operational state
    is_enabled: bool = Field(
        default=True,
        description="Whether this webhook trigger is active",
        index=True,
    )

    # Table arguments for indexes and constraints
    __table_args__ = (
        # NOTE: When adding a new webhook trigger type, also create a migration
        # to update the DB check constraint.  See 05d8708c4137 for the pattern.
        CheckConstraint(
            "trigger_type IN ('webhook_trigger', 'eda_trigger')",
            name="ck_webhook_triggers_trigger_type_valid",
        ),
        # Composite unique index: same path allowed across different trigger types
        Index("ix_webhook_triggers_type_path_unique", "trigger_type", "webhook_path", unique=True),
        # Composite index for workflow lookup
        Index("ix_webhook_triggers_workflow_id_enabled", "workflow_id", "is_enabled"),
        # GIN index on labels for JSONB containment queries
        Index(
            "ix_webhook_triggers_labels",
            "labels",
            postgresql_using="gin",
        ),
    )

    def __repr__(self) -> str:
        """Return string representation of WebhookTrigger."""
        return (
            f"<WebhookTrigger(id={self.id}, trigger_type={self.trigger_type}, "
            f"webhook_path={self.webhook_path}, workflow_id={self.workflow_id}, "
            f"trigger_node_id={self.trigger_node_id})>"
        )


# ============================================================================
# API Response Schemas (Pattern 1: Separate models with table=False)
# ============================================================================


class WebhookTriggerRead(SQLModel):
    """Schema for webhook trigger response.

    Used when returning webhook trigger data in API responses.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID
    trigger_type: str
    webhook_path: str
    workflow_id: UUID
    trigger_node_id: str
    input_schema: dict[str, Any] | None = None
    is_enabled: bool
    created_at: datetime
    updated_at: datetime
