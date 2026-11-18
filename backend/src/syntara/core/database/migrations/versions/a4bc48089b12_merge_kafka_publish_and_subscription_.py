"""merge kafka publish and subscription heads

Revision ID: a4bc48089b12
Revises: 07f34fed0845, 5802e4d4e04b
Create Date: 2026-11-16 13:38:12.943585

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "a4bc48089b12"
down_revision: str | Sequence[str] | None = ("07f34fed0845", "5802e4d4e04b")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
