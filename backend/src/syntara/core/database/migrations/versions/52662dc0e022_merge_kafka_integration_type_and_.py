"""merge kafka integration type and activity control data heads

Revision ID: 52662dc0e022
Revises: e7a1c4b92f08, e7f4a1b2c3d4
Create Date: 2026-10-21 14:22:47.074592

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "52662dc0e022"
down_revision: str | Sequence[str] | None = ("e7a1c4b92f08", "e7f4a1b2c3d4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
