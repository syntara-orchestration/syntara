"""Merge activity control data and integration synchronization heads.

Revision ID: f9a8b7c6d5e4
Revises: e7f4a1b2c3d4, 2c3d4e5f6071
Create Date: 2026-10-16
"""

from collections.abc import Sequence

revision: str = "f9a8b7c6d5e4"
down_revision: str | Sequence[str] | None = ("e7f4a1b2c3d4", "2c3d4e5f6071")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Join the two migration branches without changing the schema."""


def downgrade() -> None:
    """Allow either migration branch to be traversed independently."""
