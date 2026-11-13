"""merge Kafka Publish and subscription updates

Revision ID: 695bc441fb48
Revises: 07f34fed0845, 5802e4d4e04b
Create Date: 2026-11-13 16:26:18.325626

"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "695bc441fb48"
down_revision: str | Sequence[str] | None = ("07f34fed0845", "5802e4d4e04b")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
