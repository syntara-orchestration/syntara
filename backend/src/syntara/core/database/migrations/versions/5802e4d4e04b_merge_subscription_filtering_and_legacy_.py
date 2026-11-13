"""merge subscription filtering and legacy pause heads

Revision ID: 5802e4d4e04b
Revises: d2a6c84e9b10, fa98d2d2c869
Create Date: 2026-11-12 13:16:48.085499

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "5802e4d4e04b"
down_revision: str | Sequence[str] | None = ("d2a6c84e9b10", "fa98d2d2c869")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
