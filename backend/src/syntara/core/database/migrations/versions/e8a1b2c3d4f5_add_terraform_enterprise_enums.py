"""Add terraform_enterprise integration type and TFE node types.

Revision ID: e8a1b2c3d4f5
Revises: d5b8c2f04e71
Create Date: 2026-09-24 00:00:00.000000

Adds ``terraform_enterprise`` to the ``integration_type`` Postgres enum and
all TFE workflow node type values to the ``nodetype`` Postgres enum.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8a1b2c3d4f5"
down_revision: str | Sequence[str] | None = "d5b8c2f04e71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TFE_NODE_TYPES = (
    "tfe_create_workspace",
    "tfe_list_workspaces",
    "tfe_update_workspace",
    "tfe_delete_workspace",
    "tfe_fetch_state_outputs",
    "tfe_add_variable",
    "tfe_list_variables",
    "tfe_update_variable",
    "tfe_delete_variable",
    "tfe_upload_configuration_version",
    "tfe_trigger_run",
    "tfe_get_run_status",
    "tfe_apply_run",
    "tfe_discard_run",
    "tfe_cancel_run",
    "tfe_force_cancel_run",
    "tfe_list_runs",
    "tfe_add_run_comment",
    "tfe_list_github_installations",
    "tfe_get_github_installation",
    "tfe_link_vcs",
    "tfe_create_project",
    "tfe_list_projects",
    "tfe_get_project",
    "tfe_update_project",
    "tfe_delete_project",
    "tfe_move_workspace_to_project",
    "tfe_assign_team_permissions",
)


def upgrade() -> None:
    """Add Terraform Enterprise enum values."""
    # CUSTOM: Postgres requires ADD VALUE outside a transaction block in some versions;
    # Alembic runs in a transaction — ADD VALUE IF NOT EXISTS is supported on PG 9.3+
    # for plain ADD VALUE; IF NOT EXISTS requires PG 9.1+ for types in recent PG.
    op.execute("ALTER TYPE integration_type ADD VALUE IF NOT EXISTS 'terraform_enterprise'")
    for node_type in _TFE_NODE_TYPES:
        op.execute(f"ALTER TYPE nodetype ADD VALUE IF NOT EXISTS '{node_type}'")


def downgrade() -> None:
    """Enum value removal is not supported safely in Postgres; leave values in place."""
    # Downgrade intentionally left as a no-op: dropping enum values that may be
    # referenced by rows is unsafe. Redeploying a prior application version that
    # does not emit these values is sufficient.
