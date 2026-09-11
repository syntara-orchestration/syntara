"""FormPrompt SQLModel and FormPromptStatus enum.

This module contains the FormPrompt model representing human-in-the-loop
data collection points in workflow executions, and the associated status enumeration.
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

from sqlalchemy import Column, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import DateTime, Field, Relationship

from syntara.core.constants import FieldLimits
from syntara.core.models.base import BaseResource
from syntara.core.models.pagination import ResourcesResponse
from syntara.core.models.user_reference import UserReference
from syntara.core.utils.sqlmodel import postgres_enum_column
from syntara.forms.models.api_models import (
    FormPromptStatus,
    ResponderGroupSummary,
    ResponderUserSummary,
)
from syntara.forms.models.form_prompt_responders import (
    FormPromptResponderGroup,
    FormPromptResponderUser,
)

if TYPE_CHECKING:
    from syntara.core.models import Group, User


class BaseFormPrompt(BaseResource, table=False):
    """Base form prompt model with common fields.

    Contains all form prompt fields except responded_by, allowing for different
    representations of the responding user (UUID in database vs UserReference in API).
    """

    # Project scoping (denormalized from execution for efficient filtering)
    project_id: UUID = Field(
        foreign_key="projects.id",
        description="Project this form prompt belongs to (denormalized from execution)",
        index=True,
    )

    # User-provided identification
    name: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Human-readable name for the form prompt",
        index=True,
    )

    message: str | None = Field(
        default=None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        sa_type=String(FieldLimits.DESCRIPTION_MAX_LENGTH),  # type: ignore[call-overload]
        description="Resolved guidance message shown to responders",
    )

    # Soft reference to parent execution (no foreign key constraint)
    execution_id: UUID = Field(
        nullable=False,
        description="Parent execution ID",
        index=True,
    )

    # Form prompt identity — canvas node ID, not a Temporal or loop-iteration ID
    prompt_node_id: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Canvas node ID from the workflow definition",
    )

    loop_iteration_path: list[int] = Field(
        default_factory=list,
        sa_column=Column(JSONB, nullable=False, server_default=text("'[]'::jsonb")),
        description="Enclosing-loop indices, outermost first (empty when not inside a loop)",
    )

    # Status
    status: FormPromptStatus = Field(
        default=FormPromptStatus.PENDING,
        description="Current form prompt status",
        sa_column=postgres_enum_column(
            FormPromptStatus,
            "formpromptstatus",
            index=True,
            create_constraint=True,
            server_default=text("'pending'::formpromptstatus"),
        ),
    )

    # Timing
    timeout_at: datetime | None = Field(
        default=None,
        nullable=True,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="When this prompt expires",
        index=True,
    )

    # Form definition
    input_schema: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        description="JSON Schema Draft-07 form definition",
    )

    # Form presentation options (snapshotted at creation for renderer/submit service)
    submit_label: str | None = Field(
        default=None,
        max_length=64,
        sa_type=String(64),  # type: ignore[call-overload]
        description="Submit button label shown to the responder",
    )

    success_message: str | None = Field(
        default=None,
        max_length=500,
        sa_type=String(500),  # type: ignore[call-overload]
        description="Message shown after successful form submission",
    )

    timezone: str | None = Field(
        default=None,
        max_length=64,
        sa_type=String(64),  # type: ignore[call-overload]
        description="IANA timezone name for interpreting date/datetime field values (longest ~40 chars)",
    )

    css_override: str | None = Field(
        default=None,
        max_length=10000,
        sa_type=String(10000),  # type: ignore[call-overload]
        description="Custom CSS applied to the form view",
    )

    # Response fields (without responded_by)
    response_data: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
        description="Submitted form values",
    )

    responded_at: datetime | None = Field(
        default=None,
        nullable=True,
        sa_type=DateTime(timezone=True),  # type: ignore[call-overload]
        description="When response was submitted",
    )


class FormPrompt(BaseFormPrompt, table=True):
    """FormPrompt database model with UUID foreign key for responded_by.

    Extends BaseFormPrompt with the database-specific responded_by field
    that stores a UUID foreign key to the users table.
    """

    __tablename__ = "form_prompts"
    __table_args__ = (
        UniqueConstraint(
            "execution_id",
            "prompt_node_id",
            "loop_iteration_path",
            name="uix_execution_prompt_node_path",
        ),
        Index("ix_form_prompts_labels", "labels", postgresql_using="gin"),
    )

    # Filterable and sortable fields for API endpoints
    __filterable_fields__: ClassVar[list[str]] = [
        *BaseResource.__filterable_fields__,
        "name",
        "execution_id",
        "project_id",
        "status",
        "timeout_at",
    ]

    __sortable_fields__: ClassVar[list[str]] = [
        *BaseResource.__sortable_fields__,
        "name",
        "timeout_at",
        "responded_at",
        "status",
    ]

    # Response field - database stores UUID foreign key to users
    responded_by: UUID | None = Field(
        default=None,
        foreign_key="users.id",
        nullable=True,
        ondelete="SET NULL",
        description="User who submitted the response",
    )

    temporal_activity_id: str | None = Field(
        default=None,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Temporal activity ID to signal when this prompt is answered",
    )

    # Relationships
    responder: "User" = Relationship(
        sa_relationship_kwargs={
            "primaryjoin": "FormPrompt.responded_by == User.id",
            "foreign_keys": "[FormPrompt.responded_by]",
        },
    )

    # Many-to-many relationships through junction tables
    responder_user_records: list["User"] = Relationship(
        link_model=FormPromptResponderUser,
        sa_relationship_kwargs={"viewonly": True},
    )

    responder_group_records: list["Group"] = Relationship(
        link_model=FormPromptResponderGroup,
        sa_relationship_kwargs={"viewonly": True},
    )


class FormPromptRead(BaseFormPrompt, table=False):
    """FormPrompt API response model with typed nested fields.

    Overrides the JSONB dict fields from BaseFormPrompt with typed models
    so API consumers get proper validation and type safety. Pydantic coerces
    the raw dicts from the database into these typed models during serialization.
    """

    # Override JSONB dict fields with typed models
    loop_iteration_path: list[int] = Field(
        default_factory=list,
        description="Enclosing-loop indices, outermost first (empty when not inside a loop)",
    )

    # Responder configuration - API returns summary objects
    responder_users: list[ResponderUserSummary] = Field(
        default_factory=list,
        description="Users who can respond to this prompt (empty = any user with permission)",
    )
    responder_groups: list[ResponderGroupSummary] = Field(
        default_factory=list,
        description="Groups whose members can respond to this prompt",
    )

    # Response field - API returns UserReference object
    responded_by: UserReference | None = Field(
        default=None,
        description="User who submitted the response",
    )

    # Signal delivery status (populated only in the respond response, not persisted)
    signal_delivery_error: str | None = Field(
        default=None,
        description=(
            "Error if the workflow signal failed after a response."
            " Only present in the respond response; null on subsequent reads."
        ),
    )


# ============================================================================
# List Response
# ============================================================================


class FormPromptListResponse(ResourcesResponse[FormPromptRead]):
    """Paginated list response for form prompts."""
