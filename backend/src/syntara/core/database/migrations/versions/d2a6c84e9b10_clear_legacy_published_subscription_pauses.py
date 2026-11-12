"""Clear legacy pauses for active published subscriptions.

Revision ID: d2a6c84e9b10
Revises: 07ace57975ac

This data-only correction aligns legacy subscription state with workflow
publication after removal of separate pause/resume controls. Stop event workers
before upgrading. Published, desired and non-retired subscriptions resume under
normal placement and admission checks. Downgrade cannot reconstruct old pauses.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d2a6c84e9b10"
down_revision: str | Sequence[str] | None = "07ace57975ac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Clear pauses only for subscriptions matching the current publication."""
    # CUSTOM: Correct legacy data without changing models or source identities.
    op.execute(
        "UPDATE event_subscriptions AS subscription "
        "SET paused = false, configuration_revision = subscription.configuration_revision + 1 "
        "WHERE subscription.paused = true AND subscription.desired_enabled = true "
        "AND subscription.retired = false AND EXISTS ("
        "SELECT 1 FROM workflows AS workflow WHERE workflow.id = subscription.workflow_id "
        "AND workflow.is_enabled = true "
        "AND workflow.published_version_id = subscription.published_version_id)"
    )
    # END CUSTOM


def downgrade() -> None:
    """Preserve current activation because previous pause values are unknown."""
