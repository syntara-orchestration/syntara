"""Drop the unused namespace from stored OpenShift integration configurations.

The cluster dispatch namespace lives on execution targets since the EP cluster
refactor; the OpenShiftConfiguration.namespace field ("reserved for future
execution workloads") was never read and is removed from the model. Existing
rows would fail the configuration's extra="forbid" validation on load, so strip
the key from stored JSONB.

Revision ID: d7c2f4a8b3e9
Revises: b2c3d4e5f6a7
Create Date: 2026-11-03

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7c2f4a8b3e9"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove the obsolete namespace key from openshift configurations."""
    op.execute(
        "UPDATE integrations "
        "SET configuration = configuration - 'namespace' "
        "WHERE integration_type = 'openshift' AND configuration ? 'namespace'"
    )


def downgrade() -> None:
    """Restore a placeholder namespace; the original value is not recoverable."""
    op.execute(
        "UPDATE integrations "
        "SET configuration = configuration || "
        'CAST(\'{"namespace": "default"}\' AS jsonb) '
        "WHERE integration_type = 'openshift' AND NOT (configuration ? 'namespace')"
    )
