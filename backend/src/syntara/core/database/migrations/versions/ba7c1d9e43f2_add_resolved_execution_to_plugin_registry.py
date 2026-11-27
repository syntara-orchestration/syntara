"""Store compiled SDK binding data for custom-runner dispatch.

Revision ID: ba7c1d9e43f2
Revises: a3d4f6b8c9e0
Create Date: 2026-11-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "ba7c1d9e43f2"
down_revision: str | Sequence[str] | None = "a3d4f6b8c9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add optional compiled runtime binding metadata to registered Actions."""
    op.add_column(
        "execution_plane_plugins",
        sa.Column("resolved_execution", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Drop the compiled runtime binding metadata column."""
    op.drop_column("execution_plane_plugins", "resolved_execution")
