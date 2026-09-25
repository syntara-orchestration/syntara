"""add Kubernetes target configuration

Revision ID: c7a8e4d2f901
Revises: 9f3e1a2b4c7d
Create Date: 2026-09-21

Credentials are deliberately referenced, not persisted. The local development
registration points at a file mounted into the execution-plane container.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "c7a8e4d2f901"
down_revision: str | Sequence[str] | None = "9f3e1a2b4c7d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EP = "execution_plane"


def upgrade() -> None:
    """Add namespace and credential references for remote Kubernetes targets."""
    op.add_column(
        "execution_targets",
        sa.Column("namespace", sa.String(), nullable=False, server_default="ep-dev-workers"),
        schema=EP,
    )
    op.alter_column("execution_targets", "namespace", server_default=None, schema=EP)
    op.add_column(
        "execution_targets",
        sa.Column("credential_ref", JSONB(), nullable=False, server_default="{}"),
        schema=EP,
    )
    op.alter_column("work_items", "activity_handle", existing_type=sa.Text(), nullable=True, schema=EP)


def downgrade() -> None:
    """Remove Kubernetes target configuration."""
    op.alter_column("work_items", "activity_handle", existing_type=sa.Text(), nullable=False, schema=EP)
    op.drop_column("execution_targets", "credential_ref", schema=EP)
    op.drop_column("execution_targets", "namespace", schema=EP)
