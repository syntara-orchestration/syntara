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


def _delete_by_project(table: str) -> sa.TextClause:
    return sa.text(
        "DELETE FROM " + table + " WHERE project_id IN (SELECT id FROM projects WHERE deleted_at IS NOT NULL)"
    )


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
            "WHERE project_id IN (SELECT id FROM projects WHERE deleted_at IS NOT NULL)"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM webhook_triggers WHERE workflow_id IN "
            "(SELECT id FROM workflows WHERE project_id IN "
            "(SELECT id FROM projects WHERE deleted_at IS NOT NULL))"
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM workflow_versions WHERE workflow_id IN "
            "(SELECT id FROM workflows WHERE project_id IN "
            "(SELECT id FROM projects WHERE deleted_at IS NOT NULL))"
        )
    )
    op.execute(_delete_by_project("workflows"))

    # Credentials: capture secret_ids, delete credentials first (removes FK reference),
    # then delete their secrets and encrypted_secrets
    op.execute(
        sa.text(
            "DELETE FROM encrypted_secrets WHERE secret_id IN "
            "(SELECT secret_id FROM credentials WHERE project_id IN "
            "(SELECT id FROM projects WHERE deleted_at IS NOT NULL) AND secret_id IS NOT NULL)"
        )
    )
    op.execute(_delete_by_project("credentials"))
    op.execute(
        sa.text(
            "DELETE FROM secrets WHERE id NOT IN "
            "(SELECT secret_id FROM credentials WHERE secret_id IS NOT NULL) "
            "AND id NOT IN (SELECT secret_id FROM identity_providers WHERE secret_id IS NOT NULL)"
        )
    )

    op.execute(_delete_by_project("file_metadata"))
    op.execute(_delete_by_project("integration_project_assignments"))

    # Service account credentials (must precede service_accounts — FK has no CASCADE)
    op.execute(
        sa.text(
            "DELETE FROM service_account_credentials WHERE service_account_id IN "
            "(SELECT id FROM service_accounts WHERE project_id IN "
            "(SELECT id FROM projects WHERE deleted_at IS NOT NULL))"
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
