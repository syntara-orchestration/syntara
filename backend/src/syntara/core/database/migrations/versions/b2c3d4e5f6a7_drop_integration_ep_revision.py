"""Drop the integration EP cluster revision counter.

The EP Cluster now shares the Integration's physical UUID as its primary key, so
cluster commands are addressed by that id and need no configuration revision. This
migration only changes AO tables; installed EP clusters and targets are unaffected.

Revision ID: b2c3d4e5f6a7
Revises: 0dc4951ceb2c
Create Date: 2026-10-29

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "0dc4951ceb2c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the now-unused EP cluster revision counter."""
    op.drop_column("integrations", "execution_plane_revision")


def downgrade() -> None:
    """Restore the EP cluster revision counter."""
    op.add_column(
        "integrations",
        sa.Column("execution_plane_revision", sa.Integer(), server_default="0", nullable=False),
    )
