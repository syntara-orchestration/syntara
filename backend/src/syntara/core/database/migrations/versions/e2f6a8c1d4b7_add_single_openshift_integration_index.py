"""Add a partial unique index for OpenShift integrations.

Revision ID: e2f6a8c1d4b7
Revises: d7c2f4a8b3e9
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e2f6a8c1d4b7"
down_revision: str | Sequence[str] | None = "d7c2f4a8b3e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enforce one OpenShift integration without constraining other types."""
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
