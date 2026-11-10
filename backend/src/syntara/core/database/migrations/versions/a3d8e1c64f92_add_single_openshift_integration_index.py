"""Enforce a single OpenShift integration per Syntara instance.

Revision ID: a3d8e1c64f92
Revises: f17c2d6a9b04
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3d8e1c64f92"
down_revision: str | Sequence[str] | None = "f17c2d6a9b04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create a partial unique index after checking for existing duplicates."""
    duplicate_count = (
        op.get_bind()
        .execute(sa.text("SELECT count(*) FROM integrations WHERE integration_type = 'openshift'"))
        .scalar_one()
    )
    if duplicate_count > 1:
        msg = f"Found {duplicate_count} existing OpenShift integrations; resolve duplicates before migrating"
        raise RuntimeError(msg)

    op.create_index(
        "uq_integrations_single_openshift",
        "integrations",
        ["integration_type"],
        unique=True,
        postgresql_where=sa.text("integration_type = 'openshift'"),
    )


def downgrade() -> None:
    """Remove the single-OpenShift integration constraint."""
    op.drop_index("uq_integrations_single_openshift", table_name="integrations")
