"""add runtime_metadata to activity_execution

Revision ID: c7f2a1b9e3d4
Revises: a536880d7fa9
Create Date: 2026-11-04 00:00:00.000000

Adds a generic, nullable JSONB ``runtime_metadata`` column to
``activity_execution``. It holds intermediate, UI-relevant execution
information that becomes available before the final ``output_data`` exists
(e.g. a sub-workflow node's child execution id / workflow id / name /
version). Kept distinct from ``output_data`` (the node's final result).

Additive and backward compatible: nullable, no default, no backfill, no
index. Existing and non-sub-workflow rows stay NULL. Downgrade is lossless.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c7f2a1b9e3d4"
down_revision: str | Sequence[str] | None = "a536880d7fa9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "activity_execution",
        sa.Column("runtime_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("activity_execution", "runtime_metadata")
