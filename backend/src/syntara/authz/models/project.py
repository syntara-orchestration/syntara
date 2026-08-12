"""Project model for resource isolation.

Projects provide soft-tenant isolation for grouping and scoping resources.
Resources belong to a project and all queries are project-scoped.
"""

from typing import ClassVar

from sqlmodel import Field, Index, text

from syntara.core.models.base import NamedResource, SoftDeletableResource


class Project(NamedResource, SoftDeletableResource, table=True):
    """Project for resource isolation.

    Attributes:
        id: Primary key UUID (from BaseResource)
        name: Project name (from NamedResource, unique across non-deleted)
        description: Optional project description (from NamedResource)
        labels: JSONB key-value labels (from BaseResource)
        created_at: Creation timestamp (from BaseResource)
        updated_at: Last update timestamp (from BaseResource)
        deleted_at: Soft delete timestamp (from SoftDeletableResource)
        deleted_by: UUID of deleter (from SoftDeletableResource)
        is_default: Whether this is the default project

    """

    __tablename__ = "projects"

    __filterable_fields__: ClassVar[list[str]] = [
        *NamedResource.__filterable_fields__,
        *SoftDeletableResource.__filterable_fields__,
        "is_default",
        "is_builtin",
    ]

    __sortable_fields__: ClassVar[list[str]] = list(
        dict.fromkeys(
            [
                *NamedResource.__sortable_fields__,
                *SoftDeletableResource.__sortable_fields__,
            ]
        )
    )

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

    __table_args__ = (
        Index(
            "ix_projects_name_unique",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<Project(id={self.id}, name={self.name}, is_default={self.is_default}, is_builtin={self.is_builtin})>"
