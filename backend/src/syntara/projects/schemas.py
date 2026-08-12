"""Request/response schemas for the projects API."""

from typing import Annotated, Any

from pydantic import Field as PydanticField
from sqlmodel import Field, SQLModel

from syntara.authz.schemas import PolicyStatementSchema
from syntara.core.constants import NAME_PATTERN
from syntara.core.models.base import BaseResource
from syntara.core.models.base.query_params import BaseListParams
from syntara.core.models.pagination import ResourcesResponse

NameField = Annotated[str, PydanticField(min_length=1, max_length=255, pattern=NAME_PATTERN)]
OptionalNameField = Annotated[
    str | None, PydanticField(default=None, min_length=1, max_length=255, pattern=NAME_PATTERN)
]


class ProjectCreate(SQLModel):
    """Request body for creating a project."""

    name: NameField
    description: str | None = None
    labels: dict[str, Any] = {}


class ProjectUpdate(SQLModel):
    """Request body for updating a project."""

    name: OptionalNameField
    description: str | None = None
    labels: dict[str, Any] | None = None


class ProjectRead(BaseResource):
    """Response body for a project."""

    name: str
    description: str | None = None
    is_default: bool = False
    is_builtin: bool = False


class ProjectRoleCreate(SQLModel):
    """Request body for creating a project-scoped role (project_id comes from URL path)."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    policies: list[str] = Field(min_length=1)
    labels: dict[str, str] = {}


class ProjectListParams(BaseListParams):
    """Query parameters for listing projects."""

    name: str | None = Field(default=None, description="Filter by project name")
    is_default: bool | None = Field(default=None, description="Filter by default project status")
    is_builtin: bool | None = Field(default=None, description="Filter by built-in project status")


class ProjectListResponse(ResourcesResponse[ProjectRead]):
    """Paginated list response for projects."""


class ProjectPolicyCreate(SQLModel):
    """Request body for creating a project-scoped policy (project_id comes from URL path)."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    statements: list[PolicyStatementSchema] = Field(min_length=1)
    labels: dict[str, str] = {}
