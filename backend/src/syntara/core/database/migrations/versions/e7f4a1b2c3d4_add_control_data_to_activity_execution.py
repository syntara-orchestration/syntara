"""add internal control data to activity executions

Revision ID: e7f4a1b2c3d4
Revises: d5b8c2f04e71
Create Date: 2026-10-12 00:00:00.000000

The nullable column preserves existing activity rows and keeps routing state
available for a future retry replay implementation without changing API data.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7f4a1b2c3d4"
down_revision: str | Sequence[str] | None = "d5b8c2f04e71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add nullable control data without rewriting existing activity rows."""
    op.add_column(
        "activity_execution",
        sa.Column("control_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Remove only the control data column."""
    op.drop_column("activity_execution", "control_data")
