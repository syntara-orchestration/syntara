"""add prompt column to approval_requests

Revision ID: c7e4a91b2d03
Revises: a8f3d1e2c4b5
Create Date: 2026-08-19 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7e4a91b2d03"
down_revision: str | Sequence[str] | None = "a8f3d1e2c4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "approval_requests",
        sa.Column("prompt", sa.String(length=2000), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("approval_requests", "prompt")
