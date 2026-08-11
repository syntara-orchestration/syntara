"""Unified role assignment model.

RoleAssignment links a principal (user, service account, or group) to a
role, optionally scoped to a project.

When project_id is NULL the assignment is system-wide (global).
When project_id is set the assignment is scoped to that project.

Exactly one of ``principal_id`` (FK → principals) or ``group_id``
(FK → groups) must be set.  A CHECK constraint enforces mutual exclusion.

Resolution chain:
- Global: user -> (direct roles + groups -> roles) -> policies
- Project: user -> project role assignments -> roles -> policies (with project scope)

Roles are referenced by name (not FK) because built-in roles are not
stored in the database -- they exist only in ``role_conventions.py``.
"""

from uuid import UUID

from sqlalchemy import CheckConstraint, String, text
from sqlmodel import Field, Index

from syntara.core.constants import FieldLimits
from syntara.core.models.base import BaseResource

__all__ = ["RoleAssignment"]


class RoleAssignment(BaseResource, table=True):
    """Principal-to-role assignment, optionally scoped to a project."""

    __tablename__ = "role_assignments"

    principal_id: UUID | None = Field(
        default=None,
        foreign_key="principals.id",
        description="UUID of the user or service account (FK → principals)",
        index=True,
    )

    group_id: UUID | None = Field(
        default=None,
        foreign_key="groups.id",
        description="UUID of the group (FK → groups)",
        index=True,
    )

    role_name: str = Field(
        sa_type=String(FieldLimits.NAME_MAX_LENGTH),  # type: ignore[call-overload]
        description="Name of the assigned role",
        index=True,
    )

    project_id: UUID | None = Field(
        default=None,
        foreign_key="projects.id",
        description="Project scope (NULL = global assignment)",
        index=True,
    )

    is_builtin: bool = Field(
        default=False,
        description="Whether this is a seed-level assignment that cannot be revoked",
        index=True,
    )

    __table_args__ = (
        CheckConstraint(
            "(principal_id IS NOT NULL) != (group_id IS NOT NULL)",
            name="ck_ra_principal_xor_group",
        ),
        Index(
            "ix_ra_principal_role_global",
            "principal_id",
            "role_name",
            unique=True,
            postgresql_where=text("project_id IS NULL AND principal_id IS NOT NULL"),
        ),
        Index(
            "ix_ra_group_role_global",
            "group_id",
            "role_name",
            unique=True,
            postgresql_where=text("project_id IS NULL AND group_id IS NOT NULL"),
        ),
        Index(
            "ix_ra_principal_role_project",
            "principal_id",
            "role_name",
            "project_id",
            unique=True,
            postgresql_where=text("project_id IS NOT NULL AND principal_id IS NOT NULL"),
        ),
        Index(
            "ix_ra_group_role_project",
            "group_id",
            "role_name",
            "project_id",
            unique=True,
            postgresql_where=text("project_id IS NOT NULL AND group_id IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        target = f"principal_id={self.principal_id}" if self.principal_id else f"group_id={self.group_id}"
        return f"<RoleAssignment({target}, role_name={self.role_name}, project_id={self.project_id})>"
