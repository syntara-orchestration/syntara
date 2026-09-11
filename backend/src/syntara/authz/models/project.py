"""Project model for resource isolation.

Projects provide soft-tenant isolation for grouping and scoping resources.
Resources belong to a project and all queries are project-scoped.
"""

from typing import Any, ClassVar

from sqlmodel import Field, UniqueConstraint, text

from syntara.core.models.base import NamedResource


class Project(NamedResource, table=True):
    """Project for resource isolation (hard delete).

    Attributes:
        id: Primary key UUID (from BaseResource)
        name: Project name (from NamedResource, unique)
        description: Optional project description (from NamedResource)
        labels: JSONB key-value labels (from BaseResource)
        created_at: Creation timestamp (from BaseResource)
        updated_at: Last update timestamp (from BaseResource)
        is_default: Whether this is the default project

    """

    FIELD_SCHEMA_EXTRAS: ClassVar[dict[str, dict[str, Any]]] = {
        **NamedResource.FIELD_SCHEMA_EXTRAS,
    }

    __tablename__ = "projects"

    __filterable_fields__: ClassVar[list[str]] = [
        *NamedResource.__filterable_fields__,
        "is_default",
        "is_builtin",
    ]

    __sortable_fields__: ClassVar[list[str]] = list(dict.fromkeys(NamedResource.__sortable_fields__))

    is_default: bool = Field(
        default=False,
        description="Whether this is the default project",
        index=True,
    )
    is_builtin: bool = Field(
        default=False,
        description="Whether this is a built-in system project",
        index=True,
        sa_column_kwargs={"server_default": text("false")},
    )

    __table_args__ = (UniqueConstraint("name", name="uq_projects_name"),)

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<Project(id={self.id}, name={self.name}, is_default={self.is_default}, is_builtin={self.is_builtin})>"
