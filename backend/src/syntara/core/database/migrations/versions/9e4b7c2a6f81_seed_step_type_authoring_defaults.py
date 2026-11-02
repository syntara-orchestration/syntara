# Generated with AI assistance: Codex (OpenAI)
"""Seed editable step-type authoring grants once, without changing the schema.

Revision ID: 9e4b7c2a6f81
Revises: e7f4a1b2c3d4

CUSTOM: Alembic history preserves administrator edits and deletions. The frozen
data here must not depend on application models or the current step registry.
Downgrade is permitted only for untouched, unreferenced defaults.
"""

from typing import Any
from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "9e4b7c2a6f81"
down_revision = "e7f4a1b2c3d4"
branch_labels = None
depends_on = None

_KINDS = (
    "manual_trigger",
    "scheduled_trigger",
    "webhook_trigger",
    "eda_trigger",
    "condition",
    "converge",
    "loop",
    "switch",
    "wait",
    "aap_job_template",
    "aap_workflow_job_template",
    "agentic",
    "approval",
    "http_request",
    "script",
)
CATALOG_NAMES = tuple(f"step_type:write:{scope}:deny:{kind}" for kind in _KINDS for scope in ("any", "project"))


def _columns() -> list[sa.ColumnClause[Any]]:
    return [
        sa.column("id", sa.Uuid()),
        sa.column("is_builtin", sa.Boolean()),
        sa.column("project_id", sa.Uuid()),
        sa.column("labels", JSONB()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    ]


POLICIES = sa.table(
    "policies",
    *_columns(),
    sa.column("name", sa.String()),
    sa.column("description", sa.String()),
    sa.column("statements", JSONB()),
    sa.column("scope", sa.String()),
)
ROLES = sa.table(
    "roles",
    *_columns(),
    sa.column("name", sa.String()),
    sa.column("description", sa.String()),
    sa.column("policy_names", JSONB()),
    sa.column("scope", sa.String()),
)
ASSIGNMENTS = sa.table(
    "role_assignments",
    *_columns(),
    sa.column("role_name", sa.String()),
    sa.column("group_id", sa.Uuid()),
    sa.column("principal_id", sa.Uuid()),
)

_COMMON: dict[str, Any] = {"is_builtin": False, "project_id": None, "labels": {}}
POLICY_DEFAULT: dict[str, Any] = {
    **_COMMON,
    "id": UUID("84258468-4976-4b32-9dce-a312cbe70be0"),
    "name": "default-step-type-write",
    "description": "Allow all authenticated users and service accounts to author every step type. "
    "Deleting this policy blocks workflow authoring unless another policy grants step_type:write.",
    "statements": [{"effect": "allow", "actions": ["step_type:write"], "scope": "any"}],
    "scope": "any",
}
ROLE_DEFAULT: dict[str, Any] = {
    **_COMMON,
    "id": UUID("c63dc537-3559-4e81-a4f7-643f9cb88c34"),
    "name": "step-type-author",
    "description": "Default step-type authoring permissions for authenticated principals.",
    "policy_names": [POLICY_DEFAULT["name"]],
    "scope": "system",
}
ASSIGNMENT_DEFAULT: dict[str, Any] = {
    **_COMMON,
    "id": UUID("8bdfe429-6277-493a-b685-3ee360e09fa4"),
    "role_name": ROLE_DEFAULT["name"],
    "principal_id": None,
}


def upgrade() -> None:
    """Insert the grants and let Alembic record completion in the same transaction."""
    bind = op.get_bind()
    # Serialize the conflict checks with policy/role writes during an upgrade.
    bind.execute(sa.text("LOCK TABLE groups, policies, roles, role_assignments IN SHARE ROW EXCLUSIVE MODE"))
    conflict_policies = (
        bind.execute(
            sa.select(POLICIES.c.name).where(
                sa.or_(
                    POLICIES.c.name.in_(CATALOG_NAMES),
                    sa.and_(POLICIES.c.name == POLICY_DEFAULT["name"], POLICIES.c.project_id.is_(None)),
                    POLICIES.c.id == POLICY_DEFAULT["id"],
                )
            )
        )
        .scalars()
        .all()
    )
    conflict_roles = (
        bind.execute(
            sa.select(ROLES.c.name).where(
                sa.or_(
                    sa.and_(ROLES.c.name == ROLE_DEFAULT["name"], ROLES.c.project_id.is_(None)),
                    ROLES.c.id == ROLE_DEFAULT["id"],
                    ROLES.c.policy_names.contains([POLICY_DEFAULT["name"]]),
                )
            )
        )
        .scalars()
        .all()
    )
    conflict_assignments = (
        bind.execute(
            sa.select(ASSIGNMENTS.c.id).where(
                sa.or_(
                    ASSIGNMENTS.c.role_name == ROLE_DEFAULT["name"],
                    ASSIGNMENTS.c.id == ASSIGNMENT_DEFAULT["id"],
                )
            )
        )
        .scalars()
        .all()
    )
    if conflict_policies or conflict_roles or conflict_assignments:
        msg = (
            "Cannot install step-type defaults: existing policies="
            f"{conflict_policies}, roles={conflict_roles}, assignments={conflict_assignments}. "
            "Rename or remove conflicting records/references, then retry the upgrade. No records were adopted."
        )
        raise RuntimeError(msg)

    bind.execute(
        sa.text(
            "INSERT INTO groups (id, name, description, is_builtin, source) "
            "VALUES (gen_random_uuid(), 'authenticated', 'Implicit group for all authenticated users.', true, 'local') "
            "ON CONFLICT (name) DO NOTHING"
        )
    )
    group_id = bind.execute(sa.text("SELECT id FROM groups WHERE name = 'authenticated'")).scalar_one()
    bind.execute(POLICIES.insert().values(**POLICY_DEFAULT))
    bind.execute(ROLES.insert().values(**ROLE_DEFAULT))
    bind.execute(ASSIGNMENTS.insert().values(**ASSIGNMENT_DEFAULT, group_id=group_id))


def _untouched(bind: sa.Connection, table: sa.TableClause, expected: dict[str, Any]) -> bool:
    row = bind.execute(sa.select(table).where(table.c.id == expected["id"])).mappings().one_or_none()
    return (
        row is not None
        and row["created_at"] == row["updated_at"]
        and all(row[key] == value for key, value in expected.items())
    )


def downgrade() -> None:
    """Remove only untouched defaults; never discard an administrator's decisions."""
    bind = op.get_bind()
    bind.execute(sa.text("LOCK TABLE groups, policies, roles, role_assignments IN SHARE ROW EXCLUSIVE MODE"))
    group_id = bind.execute(sa.text("SELECT id FROM groups WHERE name = 'authenticated'")).scalar_one_or_none()
    untouched = all(
        (
            _untouched(bind, POLICIES, POLICY_DEFAULT),
            _untouched(bind, ROLES, ROLE_DEFAULT),
            _untouched(bind, ASSIGNMENTS, {**ASSIGNMENT_DEFAULT, "group_id": group_id}),
        )
    )
    extra_roles = bind.execute(
        sa.select(ROLES.c.id).where(
            ROLES.c.id != ROLE_DEFAULT["id"],
            ROLES.c.policy_names.contains([POLICY_DEFAULT["name"]]),
        )
    ).first()
    extra_assignments = bind.execute(
        sa.select(ASSIGNMENTS.c.id).where(
            ASSIGNMENTS.c.id != ASSIGNMENT_DEFAULT["id"],
            ASSIGNMENTS.c.role_name == ROLE_DEFAULT["name"],
        )
    ).first()
    if not untouched or extra_roles or extra_assignments:
        msg = (
            "Cannot downgrade step-type defaults: grants were edited, deleted, or have additional references. "
            "Keep this database revision when rolling back application code; preserve administrator changes."
        )
        raise RuntimeError(msg)
    for table, record in ((ASSIGNMENTS, ASSIGNMENT_DEFAULT), (ROLES, ROLE_DEFAULT), (POLICIES, POLICY_DEFAULT)):
        bind.execute(table.delete().where(table.c.id == record["id"]))
    # The authenticated group may predate this migration or have other assignments.
