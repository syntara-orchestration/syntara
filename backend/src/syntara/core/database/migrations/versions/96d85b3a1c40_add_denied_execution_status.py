"""Add denied as a terminal workflow execution status.

Revision ID: 96d85b3a1c40
Revises: a1750b0c9d01
Create Date: 2026-09-29 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "96d85b3a1c40"
down_revision: str | Sequence[str] | None = "a1750b0c9d01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Allow executions rejected for step permissions to be recorded as denied."""
    op.execute("ALTER TYPE workflowexecutionstatus ADD VALUE 'denied'")


def downgrade() -> None:
    """Remove denied after mapping recorded rows to the prior failed status."""
    op.execute("UPDATE executions SET status = 'failed' WHERE status = 'denied'")
    op.execute("ALTER TABLE executions ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "CREATE TYPE workflowexecutionstatus_old AS ENUM "
        "('pending', 'running', 'paused', 'completed', 'completed_with_errors', 'failed', 'cancelled')"
    )
    op.execute(
        "ALTER TABLE executions ALTER COLUMN status TYPE workflowexecutionstatus_old "
        "USING status::text::workflowexecutionstatus_old"
    )
    op.execute("DROP TYPE workflowexecutionstatus")
    op.execute("ALTER TYPE workflowexecutionstatus_old RENAME TO workflowexecutionstatus")
    op.execute("ALTER TABLE executions ALTER COLUMN status SET DEFAULT 'pending'::workflowexecutionstatus")
