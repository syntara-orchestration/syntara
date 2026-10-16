"""merge stall detection and control data migrations

Revision ID: 77e27bc9845d
Revises: 9b749f9b023e, e7f4a1b2c3d4
Create Date: 2026-10-16 13:29:04.526730

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "77e27bc9845d"
down_revision: str | Sequence[str] | None = ("9b749f9b023e", "e7f4a1b2c3d4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
