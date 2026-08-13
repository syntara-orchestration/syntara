"""Policy model for IAM-style authorization statements.

Policies contain one or more statements with effect/actions/scope/conditions
that are evaluated by the Rego policy engine.
"""

from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Index

from syntara.core.constants import FieldLimits
from syntara.core.models.base import BaseResource


class Policy(BaseResource, table=True):
    """Policy model storing IAM-style authorization statements.

    Each policy contains one or more statements that define:
    - effect: "allow" or "deny"
    - actions: list of "resource_type:action" strings (e.g. "workflow:read")
    - scope: "any" (all resources) or "self" (own resources only)
    - conditions: optional attribute-based conditions (labels, metadata)

    Attributes:
        id: Primary key UUID (from BaseResource)
        name: Unique policy name (e.g. "workflow:read:any")
        description: Optional policy description
        statements: JSONB array of statement objects
        is_builtin: Whether this is a built-in system policy
        created_at: Creation timestamp (from BaseResource)
        updated_at: Last update timestamp (from BaseResource)
        labels: JSONB key-value labels (from BaseResource)

    """

    __tablename__ = "policies"

    __filterable_fields__: ClassVar[list[str]] = [
        *BaseResource.__filterable_fields__,
        "name",
        "description",
        "is_builtin",
        "project_id",
        "scope",
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
        description="Unique policy name",
        index=True,
    )

    description: str | None = Field(
        default=None,
        max_length=FieldLimits.DESCRIPTION_MAX_LENGTH,
        sa_type=String(FieldLimits.DESCRIPTION_MAX_LENGTH),  # type: ignore[call-overload]
        description="Policy description",
    )

    statements: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_type=JSONB,
        sa_column_kwargs={"server_default": text("'[]'::jsonb")},
        description="List of policy statements (effect, actions, scope, conditions)",
    )

    is_builtin: bool = Field(
        default=False,
        description="Whether this is a built-in system policy",
        index=True,
    )

    project_id: UUID | None = Field(
        default=None,
        foreign_key="projects.id",
        description="Optional project scope (NULL = global policy)",
        index=True,
    )

    scope: str = Field(
        default="any",
        sa_type=String(20),  # type: ignore[call-overload]
        description="Policy scope: any, self, or project",
        index=True,
    )

    __table_args__ = (
        Index(
            "ix_policies_name_global_unique",
            "name",
            unique=True,
            postgresql_where=text("project_id IS NULL"),
        ),
        Index(
            "ix_policies_name_project_unique",
            "name",
            "project_id",
            unique=True,
            postgresql_where=text("project_id IS NOT NULL"),
        ),
    )

    def __repr__(self) -> str:
        """Return string representation."""
        return f"<Policy(id={self.id}, name={self.name}, is_builtin={self.is_builtin})>"

    def to_statement_dicts(self) -> list[dict[str, Any]]:
        """Convert to flat statement dicts for Rego evaluation.

        Single-statement policies use the policy name as-is.
        Multi-statement policies derive names: "policyname/0", "policyname/1".

        Returns:
            List of statement dicts with name, effect, actions, scope, conditions.

        """
        stmts: list[dict[str, Any]] = self.statements if isinstance(self.statements, list) else []
        if len(stmts) == 1:
            d: dict[str, Any] = {**stmts[0], "name": self.name}
            return [d]
        result: list[dict[str, Any]] = []
        for i, s in enumerate(stmts):
            d = {**s, "name": f"{self.name}/{i}"}
            result.append(d)
        return result
