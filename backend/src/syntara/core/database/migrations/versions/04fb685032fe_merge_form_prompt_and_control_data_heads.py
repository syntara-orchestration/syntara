"""merge form prompt and control data heads

Revision ID: 04fb685032fe
Revises: 2a78b3c49c72, e7f4a1b2c3d4
Create Date: 2026-10-16 16:15:56.620051

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "04fb685032fe"
down_revision: str | Sequence[str] | None = ("2a78b3c49c72", "e7f4a1b2c3d4")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
