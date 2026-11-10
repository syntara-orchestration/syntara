"""Drop the unused namespace from stored OpenShift integration configuration.

The namespace belongs to execution targets and is not part of the cluster
connection. Existing integration rows may still contain the old JSON key, so
remove it before the strict OpenShift configuration model is loaded.

Revision ID: f17c2d6a9b04
Revises: 8fe7495a14dc
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f17c2d6a9b04"
down_revision: str | Sequence[str] | None = "8fe7495a14dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove the obsolete namespace key from OpenShift configuration JSON."""
    op.execute(
        "UPDATE integrations "
        "SET configuration = configuration - 'namespace' "
        "WHERE integration_type = 'openshift' AND configuration ? 'namespace'"
    )


def downgrade() -> None:
    """Restore a placeholder namespace because original values are unrecoverable."""
    op.execute(
        "UPDATE integrations "
        "SET configuration = configuration || "
        'CAST(\'{"namespace": "default"}\' AS jsonb) '
        "WHERE integration_type = 'openshift' AND NOT (configuration ? 'namespace')"
    )
