"""add http integration type

Revision ID: b54b4d5053e7
Revises: a3d4f6b8c9e0
Create Date: 2026-11-28 13:59:00.858392

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b54b4d5053e7"
down_revision: str | Sequence[str] | None = "a3d4f6b8c9e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the HTTP discriminator to the existing PostgreSQL enum."""
    # CUSTOM: PostgreSQL enum values require explicit DDL.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE integration_type ADD VALUE IF NOT EXISTS 'http'")
    # END CUSTOM


def downgrade() -> None:
    """Retain the enum value because existing HTTP integrations may use it."""
    # PostgreSQL cannot remove an enum label without rebuilding dependent columns.
