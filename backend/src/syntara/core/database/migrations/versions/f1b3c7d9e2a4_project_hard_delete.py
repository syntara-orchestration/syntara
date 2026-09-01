"""project hard delete

Convert projects from soft delete to hard delete per the cascade-everything
decision (meeting 2026-08-20). Soft-deleted project rows are purged; the
deleted_at/deleted_by columns and partial unique index are dropped.

Application-level cascade in ProjectService handles child resource cleanup
before the project row itself is deleted.

Revision ID: f1b3c7d9e2a4
Revises: 7367ba3d8ccb
Create Date: 2026-08-31 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1b3c7d9e2a4"
down_revision: str | Sequence[str] | None = "7367ba3d8ccb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SOFT_DELETED = "SELECT id FROM projects WHERE deleted_at IS NOT NULL"


def _delete_by_project(table: str) -> sa.TextClause:
    return sa.text("DELETE FROM " + table + f" WHERE project_id IN ({_SOFT_DELETED})")


def upgrade() -> None:
    """Purge soft-deleted projects, drop soft-delete columns and partial index."""
    # CUSTOM: Cascade-delete child resources of soft-deleted projects before purging.
    # Order respects FK constraints.

    op.execute(_delete_by_project("approval_requests"))
    op.execute(_delete_by_project("invocations"))
    op.execute(_delete_by_project("executions"))

    # Workflows: disable, null published_version_id, delete triggers/versions, then workflows
    # Setting is_enabled = false is required by ck_workflows_is_enabled_published_version_id
    op.execute(
        sa.text(
            "UPDATE workflows SET published_version_id = NULL, is_enabled = false "
            f"WHERE project_id IN ({_SOFT_DELETED})"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM webhook_triggers WHERE workflow_id IN "
            f"(SELECT id FROM workflows WHERE project_id IN ({_SOFT_DELETED}))"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM workflow_versions WHERE workflow_id IN "
            f"(SELECT id FROM workflows WHERE project_id IN ({_SOFT_DELETED}))"
        )
    )
    op.execute(_delete_by_project("workflows"))

    # Credentials + secrets: scoped cleanup.
    # Skip credentials referenced by a live integration — ON DELETE RESTRICT on
    # integrations.management_credential_id would fail the migration. Those
    # credentials (and their secrets) stay; the admin must reassign the
    # integration's credential and re-run the migration.
    #
    # Capture secret_ids BEFORE deleting credentials so the secret deletion
    # is scoped to this migration's projects, not a global orphan sweep.
    _integration_refs = "SELECT management_credential_id FROM integrations WHERE management_credential_id IS NOT NULL"
    op.execute(
        sa.text(
            "CREATE TEMP TABLE _purge_secret_ids AS "
            "SELECT DISTINCT secret_id FROM credentials "
            f"WHERE project_id IN ({_SOFT_DELETED}) "
            "AND secret_id IS NOT NULL "
            f"AND id NOT IN ({_integration_refs})"
        )
    )
    op.execute(sa.text("DELETE FROM encrypted_secrets WHERE secret_id IN (SELECT secret_id FROM _purge_secret_ids)"))
    op.execute(
        sa.text(
            "UPDATE credentials SET secret_id = NULL "
            f"WHERE project_id IN ({_SOFT_DELETED}) "
            f"AND id NOT IN ({_integration_refs})"
        )
    )
    op.execute(
        sa.text(f"DELETE FROM credentials WHERE project_id IN ({_SOFT_DELETED}) AND id NOT IN ({_integration_refs})")
    )
    # Delete only the captured secrets — scoped, not a global orphan sweep.
    # Exclude any secret still referenced by an identity provider.
    op.execute(
        sa.text(
            "DELETE FROM secrets WHERE id IN (SELECT secret_id FROM _purge_secret_ids) "
            "AND id NOT IN "
            "(SELECT secret_id FROM identity_providers WHERE secret_id IS NOT NULL)"
        )
    )
    op.execute(sa.text("DROP TABLE IF EXISTS _purge_secret_ids"))

    op.execute(_delete_by_project("file_metadata"))
    op.execute(_delete_by_project("integration_project_assignments"))

    # Service account credentials (must precede service_accounts — FK has no CASCADE)
    op.execute(
        sa.text(
            "DELETE FROM service_account_credentials WHERE service_account_id IN "
            f"(SELECT id FROM service_accounts WHERE project_id IN ({_SOFT_DELETED}))"
        )
    )
    op.execute(_delete_by_project("service_accounts"))
    op.execute(_delete_by_project("role_assignments"))
    op.execute(_delete_by_project("roles"))
    op.execute(_delete_by_project("policies"))

    # Purge soft-deleted project rows
    op.execute(sa.text("DELETE FROM projects WHERE deleted_at IS NOT NULL"))
    # END CUSTOM

    # Drop partial unique index and replace with plain unique constraint
    op.drop_index("ix_projects_name_unique", table_name="projects")
    op.create_unique_constraint("uq_projects_name", "projects", ["name"])

    # Drop indexes on deleted_at/deleted_by before dropping columns
    op.drop_index(op.f("ix_projects_deleted_at"), table_name="projects")
    op.drop_index(op.f("ix_projects_deleted_by"), table_name="projects")

    # Drop soft-delete columns
    op.drop_column("projects", "deleted_at")
    op.drop_column("projects", "deleted_by")


def downgrade() -> None:
    """Restore soft-delete columns, indexes, and partial unique index.

    WARNING: Rows purged by upgrade() are NOT recoverable.
    """
    op.add_column("projects", sa.Column("deleted_by", sa.UUID(), nullable=True))
    op.add_column("projects", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_index(op.f("ix_projects_deleted_at"), "projects", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_projects_deleted_by"), "projects", ["deleted_by"], unique=False)

    op.drop_constraint("uq_projects_name", "projects", type_="unique")
    op.create_index(
        "ix_projects_name_unique",
        "projects",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_foreign_key("projects_deleted_by_fkey", "projects", "users", ["deleted_by"], ["id"])
