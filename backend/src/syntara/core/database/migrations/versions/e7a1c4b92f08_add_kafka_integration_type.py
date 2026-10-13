"""add kafka value to integration_type enum

Revision ID: e7a1c4b92f08
Revises: d5b8c2f04e71
Create Date: 2026-10-05 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a1c4b92f08"
down_revision: str | Sequence[str] | None = "d5b8c2f04e71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # CUSTOM: Postgres enum values are not added by autogenerate
    op.execute("ALTER TYPE integration_type ADD VALUE IF NOT EXISTS 'kafka'")
    # END CUSTOM


def downgrade() -> None:
    """Leave the enum value in place.

    PostgreSQL cannot drop a single enum label without recreating the type
    and rewriting every column that uses it.
    """
