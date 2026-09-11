"""add loop_iteration_path unique constraint for approval requests

Revision ID: a8f3d1e2c4b5
Revises: 4ca3cbf8652a
Create Date: 2026-08-21 00:00:00.000000

Loop-body approvals keep the canvas ``approval_node_id`` and distinguish
iterations with ``loop_iteration_path``. ``temporal_activity_id`` is stored
at create so decide/signal never recomputes the Temporal ID from the path.

Downgrade recreates ``uix_execution_approval_node`` on
``(execution_id, approval_node_id)`` and will fail if two rows share that
pair with different ``loop_iteration_path`` values.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a8f3d1e2c4b5"
down_revision: str | Sequence[str] | None = "4ca3cbf8652a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # CUSTOM: JSONB default, backfill, and unique-constraint swap are not a
    # plain autogenerate-safe column add.
    op.add_column(
        "approval_requests",
        sa.Column(
            "loop_iteration_path",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "approval_requests",
        sa.Column("temporal_activity_id", sa.String(length=255), nullable=True),
    )
    op.execute(sa.text("UPDATE approval_requests SET temporal_activity_id = approval_node_id"))
    op.drop_constraint("uix_execution_approval_node", "approval_requests", type_="unique")
    op.create_unique_constraint(
        "uix_execution_approval_node_path",
        "approval_requests",
        ["execution_id", "approval_node_id", "loop_iteration_path"],
    )
    # END CUSTOM


def downgrade() -> None:
    """Downgrade schema."""
    # CUSTOM: reverse unique-constraint swap before dropping columns
    op.drop_constraint("uix_execution_approval_node_path", "approval_requests", type_="unique")
    op.create_unique_constraint(
        "uix_execution_approval_node",
        "approval_requests",
        ["execution_id", "approval_node_id"],
    )
    op.drop_column("approval_requests", "temporal_activity_id")
    op.drop_column("approval_requests", "loop_iteration_path")
    # END CUSTOM
