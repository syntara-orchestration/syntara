"""Workflow SQLModel for workflow definitions and metadata.

This module provides the Workflow table model and API request/response schemas following
SQLModel Pattern 1 (separate models with table=False for API operations).
"""

from datetime import datetime
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

from pydantic import ConfigDict
from sqlalchemy import UniqueConstraint
from sqlmodel import CheckConstraint, Field, Index, Relationship, SQLModel, text

from syntara.core.constants import FieldLimits
from syntara.core.models.base.named import NamedResource
from syntara.core.models.base.user_owned import UserOwnedResource
from syntara.core.models.pagination import ResourcesResponse
from syntara.workflows.models.validation_finding import ValidationResult
from syntara.workflows.models.workflow_definition import WorkflowDefinition

if TYPE_CHECKING:
    from syntara.workflows.models.execution import Execution
    from syntara.workflows.models.workflow_version import WorkflowVersion, WorkflowVersionRead


class Workflow(NamedResource, UserOwnedResource, table=True):
    """Workflow model representing complete automation processes.

    Uses hard deletes per the "Hard Deletes Only" decision record.

    Attributes:
        id: Primary key UUID (from BaseResource)
        name: Human-readable workflow name (from NamedResource, unique per project)
        description: Optional workflow description (from NamedResource)
        labels: JSONB key-value labels for categorization (from BaseResource)
        created_at: Timestamp of workflow creation (from BaseResource)
        updated_at: Timestamp of last update (from BaseResource)
        created_by: UUID of user who created this workflow (from UserOwnedResource)
        updated_by: UUID of user who last updated this workflow (from UserOwnedResource)
        current_version: Current active version number
        is_enabled: Whether workflow is enabled for execution

    Relationships:
        versions: All versions of this workflow (CASCADE on delete)
        executions: All executions of this workflow (CASCADE on delete)

    """

    FIELD_SCHEMA_EXTRAS: ClassVar[dict[str, dict[str, Any]]] = {
        **NamedResource.FIELD_SCHEMA_EXTRAS,
        **UserOwnedResource.FIELD_SCHEMA_EXTRAS,
    }

    __tablename__ = "workflows"

    __filterable_fields__: ClassVar[list[str]] = list(
        dict.fromkeys(
            [
                *NamedResource.__filterable_fields__,
                *UserOwnedResource.__filterable_fields__,
                "is_builtin",
                "is_enabled",
                "has_validation_issues",
                "published_version_id",
                "project_id",
            ]
        )
    )

    __sortable_fields__: ClassVar[list[str]] = list(
        dict.fromkeys(
            [
                *NamedResource.__sortable_fields__,
                *UserOwnedResource.__sortable_fields__,
                "is_enabled",
            ]
        )
    )

    # Workflow-specific fields
    current_version: int = Field(
        default=1,
        description="Current active version number",
        index=True,
    )

    is_enabled: bool = Field(
        default=False,
        description="Derived field: True when a version is published. Managed by publish/unpublish.",
        index=True,
    )

    published_version_id: UUID | None = Field(
        default=None,
        foreign_key="workflow_versions.id",
        description="FK to the currently published workflow version",
        index=True,
    )

    is_builtin: bool = Field(
        default=False,
        description="Whether this is a built-in workflow",
        index=True,
        sa_column_kwargs={"server_default": text("false")},
    )

    has_validation_issues: bool = Field(
        default=False,
        description="True when the current draft has validation errors or warnings",
        sa_column_kwargs={"server_default": text("false")},
    )

    project_id: UUID = Field(
        foreign_key="projects.id",
        description="Project namespace for resource isolation",
        index=True,
    )

    # Relationships — DB handles CASCADE on delete; passive_deletes tells ORM not to null FKs
    versions: list["WorkflowVersion"] = Relationship(
        back_populates="workflow",
        cascade_delete=True,
        sa_relationship_kwargs={"foreign_keys": "WorkflowVersion.workflow_id", "passive_deletes": True},
    )

    executions: list["Execution"] = Relationship(
        back_populates="workflow",
        cascade_delete=True,
        sa_relationship_kwargs={"passive_deletes": True},
    )

    __table_args__ = (
        Index("ix_workflows_created_by_enabled", "created_by", "is_enabled"),
        Index(
            "ix_workflows_labels",
            "labels",
            postgresql_using="gin",
        ),
        UniqueConstraint("name", "project_id", name="uq_workflows_name_project"),
        CheckConstraint(
            "(published_version_id IS NULL) = (NOT is_enabled)",
            name="ck_workflows_is_enabled_published_version_id",
        ),
    )

    def __repr__(self) -> str:
        """Return string representation of Workflow.

        Returns:
            String representation

        """
        return f"<Workflow(id={self.id}, name={self.name}, version={self.current_version})>"

    def increment_version(self) -> int:
        """Increment current version and return new version number.

        Returns:
            New version number

        """
        self.current_version += 1
        return self.current_version


# ============================================================================
# API Request/Response Schemas (Pattern 1: Separate models with table=False)
# ============================================================================


class WorkflowBase(SQLModel):
    """Base schema with shared workflow fields (used for inheritance)."""

    name: str = Field(..., min_length=1, max_length=255, description="Workflow name")
    description: str | None = Field(
        None, max_length=FieldLimits.DESCRIPTION_MAX_LENGTH, description="Workflow description"
    )
    labels: dict[str, Any] = Field(default_factory=dict, description="Workflow labels")


class WorkflowCreate(WorkflowBase):
    """Schema for creating a new workflow (POST /workflows).

    Excludes auto-generated fields: id, created_at, updated_at, created_by (set by backend).
    Pydantic tries to parse workflow_definition as WorkflowDefinition first;
    on failure, the raw dict falls through to the service-level validator.
    """

    workflow_definition: WorkflowDefinition | dict[str, Any] = Field(..., description="Workflow definition object")
    project_id: UUID = Field(..., description="Project to assign workflow to")
    is_import: bool = Field(
        default=False,
        description="When true, unavailable LLM models are cleared with warnings "
        "instead of rejecting the request. Use when importing workflows from other instances.",
    )


class WorkflowUpdate(SQLModel):
    """Schema for updating workflow (PATCH /workflows/{id}).

    All fields are optional for partial updates.
    Supports metadata updates and workflow definition updates (creates new version).
    Pydantic tries to parse workflow_definition as WorkflowDefinition first;
    on failure, the raw dict falls through to the service-level validator.
    """

    project_id: UUID | None = Field(
        None, description="Project ID (immutable after creation; rejected if different from stored value)"
    )
    name: str | None = Field(None, min_length=1, max_length=255, description="Update workflow name")
    description: str | None = Field(
        None, max_length=FieldLimits.DESCRIPTION_MAX_LENGTH, description="Update workflow description"
    )
    labels: dict[str, Any] | None = Field(None, description="Update workflow labels")
    workflow_definition: WorkflowDefinition | dict[str, Any] | None = Field(
        None, description="New workflow definition (auto-creates version)"
    )
    change_description: str | None = Field(None, description="Description of changes for version history")
    expected_version: int | None = Field(
        None,
        description="Version the client was editing. If the server's current_version is higher, returns 409 Conflict.",
    )


class WorkflowRead(WorkflowBase):
    """Schema for workflow response (GET /workflows/{id}).

    Includes all fields from the database table model.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(from_attributes=True)  # type: ignore[assignment]

    id: UUID
    current_version: int
    is_builtin: bool = False
    is_enabled: bool
    has_validation_issues: bool = False
    validation_result: ValidationResult | None = Field(
        default=None,
        description=(
            "Validation findings from the last save operation. "
            "Only included in create/update responses; use has_validation_issues for the durable indicator."
        ),
    )
    published_version_id: UUID | None = None
    published_version_number: int | None = None
    created_by: UUID
    project_id: UUID
    created_at: datetime
    updated_at: datetime


class WorkflowReadWithVersion(WorkflowRead):
    """Schema for workflow response with current version details.

    Used when retrieving a single workflow to include the active workflow definition.
    """

    version: "WorkflowVersionRead" = Field(..., description="Current active version details")


class PublishWorkflowVersionResponse(WorkflowReadWithVersion):
    """Publish endpoint response — extends WorkflowReadWithVersion with a warning field."""

    warning: str = Field(
        default="",
        description="Non-fatal warning from the publish operation",
    )


# ============================================================================
# List Response
# ============================================================================


class WorkflowListResponse(ResourcesResponse[WorkflowRead]):
    """Paginated list response for workflows."""
