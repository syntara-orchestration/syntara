"""workflow hard deletes

Convert workflows, workflow_versions, and executions from soft delete
to hard delete per the "Hard Deletes Only" decision record.

Strategy: cascade-delete executions and versions with their parent workflow.

Revision ID: 7367ba3d8ccb
Revises: a986f158ce16
Create Date: 2026-07-28 10:44:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7367ba3d8ccb"
down_revision: str | Sequence[str] | None = "a986f158ce16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove soft-deleted rows, change FK rules, drop deleted_at/deleted_by columns."""
    # CUSTOM: Null out published_version_id for soft-deleted workflows (self-referential FK).
    op.execute(
        sa.text("UPDATE workflows SET published_version_id = NULL, is_enabled = false WHERE deleted_at IS NOT NULL")
    )

    # CUSTOM: Clean up ApprovalRequests referencing executions about to be purged
    # (soft reference, no FK constraint — won't cascade automatically).
    op.execute(
        sa.text(
            "DELETE FROM approval_requests WHERE execution_id IN "
            "(SELECT id FROM executions WHERE deleted_at IS NOT NULL "
            "OR workflow_id IN (SELECT id FROM workflows WHERE deleted_at IS NOT NULL))"
        )
    )

    # CUSTOM: Purge soft-deleted executions (activity_executions cascade via DB).
    op.execute(sa.text("DELETE FROM executions WHERE deleted_at IS NOT NULL"))

    # CUSTOM: Delete executions referencing soft-deleted workflows.
    # Safety check: warn if any non-terminal executions will be purged.
    conn = op.get_bind()
    non_terminal_count = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM executions "
            "WHERE workflow_id IN (SELECT id FROM workflows WHERE deleted_at IS NOT NULL) "
            # Mirrors TERMINAL_EXECUTION_STATUSES (syntara.workflows.models.execution) as of this
            # migration's authorship date. Migrations must hardcode literal values rather than
            # import application code — do not update this list if the enum changes later.
            "AND status NOT IN ('completed', 'completed_with_errors', 'failed', 'cancelled')"
        )
    ).scalar()
    if non_terminal_count:
        import logging  # noqa: PLC0415

        logging.getLogger("alembic.runtime.migration").warning(
            "Purging %d non-terminal execution(s) belonging to soft-deleted workflows. "
            "These may represent in-flight Temporal workflows that will become untrackable.",
            non_terminal_count,
        )
    op.execute(
        sa.text("DELETE FROM executions WHERE workflow_id IN (SELECT id FROM workflows WHERE deleted_at IS NOT NULL)")
    )

    # CUSTOM: Purge soft-deleted workflow versions.
    op.execute(sa.text("DELETE FROM workflow_versions WHERE deleted_at IS NOT NULL"))

    # CUSTOM: Delete live versions still referencing soft-deleted workflows
    # (old NO ACTION FK would block the workflow purge otherwise).
    op.execute(
        sa.text(
            "DELETE FROM workflow_versions WHERE workflow_id IN (SELECT id FROM workflows WHERE deleted_at IS NOT NULL)"
        )
    )

    # CUSTOM: Purge soft-deleted workflows (webhook_triggers and publish_events cascade via DB).
    op.execute(sa.text("DELETE FROM workflows WHERE deleted_at IS NOT NULL"))
    # END CUSTOM

    # -- executions: change workflow_id FK from RESTRICT to CASCADE --
    op.drop_constraint("executions_workflow_id_fkey", "executions", type_="foreignkey")
    op.create_foreign_key(
        "executions_workflow_id_fkey", "executions", "workflows", ["workflow_id"], ["id"], ondelete="CASCADE"
    )

    # -- executions: change workflow_version_id FK from RESTRICT to CASCADE --
    op.drop_constraint("executions_workflow_version_id_fkey", "executions", type_="foreignkey")
    op.create_foreign_key(
        "executions_workflow_version_id_fkey",
        "executions",
        "workflow_versions",
        ["workflow_version_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # -- workflow_versions: change workflow_id FK from NO ACTION to CASCADE --
    op.drop_constraint("workflow_versions_workflow_id_fkey", "workflow_versions", type_="foreignkey")
    op.create_foreign_key(
        "workflow_versions_workflow_id_fkey",
        "workflow_versions",
        "workflows",
        ["workflow_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # -- workflows: convert partial unique index to plain unique constraint --
    op.drop_index(
        "ix_workflows_name_project_unique",
        table_name="workflows",
    )
    op.create_unique_constraint("uq_workflows_name_project", "workflows", ["name", "project_id"])

    # -- Drop indexes on deleted_at/deleted_by before dropping columns --
    op.drop_index(op.f("ix_workflows_deleted_at"), table_name="workflows")
    op.drop_index(op.f("ix_workflows_deleted_by"), table_name="workflows")
    op.drop_index(op.f("ix_workflow_versions_deleted_at"), table_name="workflow_versions")
    op.drop_index(op.f("ix_workflow_versions_deleted_by"), table_name="workflow_versions")
    op.drop_index(op.f("ix_executions_deleted_at"), table_name="executions")
    op.drop_index(op.f("ix_executions_deleted_by"), table_name="executions")

    # -- Drop deleted_at/deleted_by columns from all three tables --
    op.drop_column("workflows", "deleted_at")
    op.drop_column("workflows", "deleted_by")
    op.drop_column("workflow_versions", "deleted_at")
    op.drop_column("workflow_versions", "deleted_by")
    op.drop_column("executions", "deleted_at")
    op.drop_column("executions", "deleted_by")


def downgrade() -> None:
    """Restore soft-delete columns and original FK constraints.

    WARNING: This restores schema only. Rows purged by upgrade() (previously
    soft-deleted workflows/versions/executions) are NOT recoverable.
    """
    # Re-add deleted_at/deleted_by columns
    op.add_column("executions", sa.Column("deleted_by", sa.UUID(), nullable=True))
    op.add_column("executions", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("workflow_versions", sa.Column("deleted_by", sa.UUID(), nullable=True))
    op.add_column("workflow_versions", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("workflows", sa.Column("deleted_by", sa.UUID(), nullable=True))
    op.add_column("workflows", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    # Recreate indexes on restored columns (required for full downgrade chain)
    op.create_index(op.f("ix_executions_deleted_at"), "executions", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_executions_deleted_by"), "executions", ["deleted_by"], unique=False)
    op.create_index(op.f("ix_workflow_versions_deleted_at"), "workflow_versions", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_workflow_versions_deleted_by"), "workflow_versions", ["deleted_by"], unique=False)
    op.create_index(op.f("ix_workflows_deleted_at"), "workflows", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_workflows_deleted_by"), "workflows", ["deleted_by"], unique=False)

    # Restore partial unique index
    op.drop_constraint("uq_workflows_name_project", "workflows", type_="unique")
    op.create_index(
        "ix_workflows_name_project_unique",
        "workflows",
        ["name", "project_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Restore workflow_versions FK (NO ACTION)
    op.drop_constraint("workflow_versions_workflow_id_fkey", "workflow_versions", type_="foreignkey")
    op.create_foreign_key(
        "workflow_versions_workflow_id_fkey", "workflow_versions", "workflows", ["workflow_id"], ["id"]
    )

    # Restore executions FKs (RESTRICT, NOT NULL)
    op.drop_constraint("executions_workflow_version_id_fkey", "executions", type_="foreignkey")
    op.create_foreign_key(
        "executions_workflow_version_id_fkey",
        "executions",
        "workflow_versions",
        ["workflow_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.drop_constraint("executions_workflow_id_fkey", "executions", type_="foreignkey")
    op.create_foreign_key(
        "executions_workflow_id_fkey", "executions", "workflows", ["workflow_id"], ["id"], ondelete="RESTRICT"
    )

    # Restore deleted_by FK constraints
    op.create_foreign_key("workflows_deleted_by_fkey", "workflows", "users", ["deleted_by"], ["id"])
    op.create_foreign_key("workflow_versions_deleted_by_fkey", "workflow_versions", "users", ["deleted_by"], ["id"])
    op.create_foreign_key("executions_deleted_by_fkey", "executions", "users", ["deleted_by"], ["id"])
