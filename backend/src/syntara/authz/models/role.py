"""Role model for authorization policy bundles.

Roles group policies together and are assigned to users.
Built-in roles exist only in ``role_conventions.py`` — this table
stores only custom (user-created) roles.  Each role carries its
policy references as a list of names in ``policy_names``.
"""

from typing import ClassVar
from uuid import UUID

from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Index

from syntara.core.constants import FieldLimits
from syntara.core.models.base import BaseResource


class Role(BaseResource, table=True):
    """Role model representing a bundle of policies.

    Policy associations are stored as ``policy_names`` (JSONB list of
    strings).  Each name can reference either a built-in policy (resolved
    from ``role_conventions.py``) or a custom policy (resolved from the
    ``policies`` table).
    """

    __tablename__ = "roles"

    __filterable_fields__: ClassVar[list[str]] = [
        *BaseResource.__filterable_fields__,
        "name",
        "description",
        "is_builtin",
        "project_id",
        "scope",
        "policy_name",
    ]

    __sortable_fields__: ClassVar[list[str]] = [
        *BaseResource.__sortable_fields__,
        "name",
        "is_builtin",
        "scope",
        "project_id",
    ]

    name: str = Field(
        min_length=1,
        max_length=FieldLimits.NAME_MAX_LENGTH,
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Unique role name",
        index=True,
    )

    description: str | None = Field(
        default=None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        sa_type=String(FieldLimits.DESCRIPTION_MAX_LENGTH),  # type: ignore[call-overload]
        description="Role description",
    )

    is_builtin: bool = Field(
        default=False,
        description="Whether this is a built-in system role",
        index=True,
    )

    project_id: UUID | None = Field(
        default=None,
        foreign_key="projects.id",
        description="Optional project scope (NULL = global role)",
        index=True,
    )

    scope: str = Field(
        default="system",
        sa_type=String(20),  # type: ignore[call-overload]
        description="Role scope: system or project",
        index=True,
    )

    policy_names: list[str] = Field(
        default_factory=list,
        sa_type=JSONB,
        sa_column_kwargs={"server_default": text("'[]'::jsonb")},
        description="Policy names attached to this role",
    )

    __table_args__ = (
        Index(
            "ix_roles_name_global_unique",
            "name",
            unique=True,
            postgresql_where=text("project_id IS NULL"),
        ),
        Index(
            "ix_roles_name_project_unique",
            "name",
            "project_id",
            unique=True,
            postgresql_where=text("project_id IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<Role(id={self.id}, name={self.name}, is_builtin={self.is_builtin})>"
