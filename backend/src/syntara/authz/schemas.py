"""Request/response schemas for the policies and roles API."""

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import Field as PydanticField
from pydantic import computed_field, field_validator
from sqlmodel import Field, SQLModel

from syntara.core.constants import NAME_PATTERN
from syntara.core.exceptions import SafeValueError
from syntara.core.models.base import BaseListParams
from syntara.core.models.pagination import ResourcesResponse

NameField = Annotated[str, PydanticField(min_length=1, max_length=255, pattern=NAME_PATTERN)]
OptionalNameField = Annotated[
    str | None, PydanticField(default=None, min_length=1, max_length=255, pattern=NAME_PATTERN)
]

# ---------------------------------------------------------------------------
# Policy schemas
# ---------------------------------------------------------------------------

VALID_SCOPES = {"any", "self", "project", "own"}
VALID_EFFECTS = {"allow"}


class PolicyStatementSchema(SQLModel):
    """A single policy statement."""

    effect: str = Field(description="allow or deny")
    actions: list[str] = Field(description="List of resource_type:action strings")
    scope: str = Field(description="any, self, or project")
    conditions: dict[str, Any] | None = Field(default=None, description="Optional attribute-based conditions")

    @field_validator("effect")
    @classmethod
    def validate_effect(cls, v: str) -> str:
        """Validate that effect is one of the allowed values."""
        if v not in VALID_EFFECTS:
            msg = f"Invalid effect '{v}'. Only 'allow' is currently supported."
            raise SafeValueError(msg)
        return v

    @field_validator("scope")
    @classmethod
    def validate_scope(cls, v: str) -> str:
        """Validate that scope is one of the allowed values."""
        if v not in VALID_SCOPES:
            msg = f"scope must be one of {sorted(VALID_SCOPES)}, got '{v}'"
            raise ValueError(msg)
        return v


class PolicyCreate(SQLModel):
    """Request body for creating a policy."""

    name: NameField
    description: str | None = None
    statements: list[PolicyStatementSchema] = Field(min_length=1)
    labels: dict[str, str] = {}
    project_id: UUID | None = None


class PolicyUpdate(SQLModel):
    """Request body for updating a policy (partial)."""

    name: OptionalNameField
    description: str | None = None
    statements: list[PolicyStatementSchema] | None = None
    labels: dict[str, str] | None = None


class PolicyRead(SQLModel):
    """Response body for a policy."""

    id: UUID
    name: str
    description: str | None = None
    statements: list[dict[str, Any]] = []
    is_builtin: bool = False
    project_id: UUID | None = None
    scope: str = "any"
    labels: dict[str, Any] = {}
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_system_scoped(self) -> bool:
        """True when the policy is not scoped to a specific project."""
        return self.project_id is None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_project_eligible(self) -> bool:
        """True when the policy belongs to a project or is a project-scoped builtin."""
        return self.project_id is not None or self.scope in ("project", "own")


class PolicyListResponse(ResourcesResponse[PolicyRead]):
    """Paginated list response for policies."""


class PolicyListParams(BaseListParams):
    """Query parameters for listing policies."""

    name: str | None = Field(default=None, description="Filter by name")
    is_builtin: bool | None = Field(default=None, description="Filter by builtin status")
    project_id: UUID | None = Field(default=None, description="Filter by project scope")
    project_eligible: bool | None = Field(
        default=None,
        description="When true, return only system-scoped policies eligible for project roles",
    )
    scope: str | None = Field(default=None, description="Filter by policy scope (any, self, or project)")


# ---------------------------------------------------------------------------
# Role schemas
# ---------------------------------------------------------------------------


class RoleCreate(SQLModel):
    """Request body for creating a role."""

    name: NameField
    description: str | None = None
    policies: list[str] = Field(min_length=1)
    labels: dict[str, str] = {}
    project_id: UUID | None = None


class RoleUpdate(SQLModel):
    """Request body for updating a role (partial)."""

    name: OptionalNameField
    description: str | None = None
    policies: list[str] | None = None
    labels: dict[str, str] | None = None


class RoleRead(SQLModel):
    """Response body for a role."""

    id: UUID
    name: str
    description: str | None = None
    policies: list[str] = []
    is_builtin: bool = False
    project_id: UUID | None = None
    scope: str = "system"
    labels: dict[str, Any] = {}
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_system_scoped(self) -> bool:
        """True when the role is not scoped to a specific project."""
        return self.project_id is None


class RoleListResponse(ResourcesResponse[RoleRead]):
    """Paginated list response for roles."""


class RoleListParams(BaseListParams):
    """Query parameters for listing roles."""

    name: str | None = Field(default=None, description="Filter by name")
    is_builtin: bool | None = Field(default=None, description="Filter by builtin status")
    project_id: UUID | None = Field(default=None, description="Filter by project scope")
    scope: str | None = Field(default=None, description="Filter by role scope (system or project)")
    policy_name: str | None = Field(default=None, description="Filter by policy name")
