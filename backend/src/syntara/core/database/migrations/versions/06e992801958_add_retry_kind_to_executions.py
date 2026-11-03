"""add retry_kind to executions

Adds retry_kind column to executions table for durable retry classification.

- NULL: Fresh execution (not a retry)
- 'plain': Retry via retry_execution() (complete workflow retry)
- 'from_failure': Retry via retry_from_failure() (replay from failed state)
- 'unknown': Legacy retry with indeterminate classification

No backfill: Existing retry rows remain NULL until reclassified.

Revision ID: 06e992801958
Revises: 9b749f9b023e
Create Date: 2026-11-03 09:30:57.579620

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "06e992801958"
down_revision: str | Sequence[str] | None = "9b749f9b023e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add retry_kind column with bounded values."""
    op.add_column(
        "executions",
        sa.Column(
            "retry_kind",
            sa.String(length=16),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "ck_executions_retry_kind",
        "executions",
        "retry_kind IN ('plain', 'from_failure', 'unknown') OR retry_kind IS NULL",
    )


def downgrade() -> None:
    """Remove retry_kind column."""
    op.drop_constraint("ck_executions_retry_kind", "executions", type_="check")
    op.drop_column("executions", "retry_kind")
