"""Wake legacy availability failures after switching to automatic scheduling retry.

Revision ID: b7e32a91c604
Revises: c4a8f17d2e93

Stop ingestion/recovery workers before applying this data correction. Only
unowned prepared deliveries parked by the old runtime_unavailable failure path
are made due. Preserve frozen bindings, start-attempt history and retry budgets.
Execution scheduling metadata receives the same retry timestamp atomically.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7e32a91c604"
down_revision: str | Sequence[str] | None = "c4a8f17d2e93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make only the old permanent availability failures eligible for normal retry."""
    # CUSTOM: Correct persisted retry state without changing delivery identities
    # or weakening normal runtime availability and acceptance-history checks.
    op.execute(
        "WITH awakened AS ("
        "UPDATE event_deliveries AS delivery SET next_attempt_at = clock_timestamp() "
        "WHERE delivery.state = 'in_progress' AND delivery.frozen_binding IS NOT NULL "
        "AND delivery.execution_id IS NOT NULL AND delivery.last_error_code = 'runtime_unavailable' "
        "AND delivery.next_attempt_at = TIMESTAMPTZ '9999-12-30 00:00:00+00' "
        "AND delivery.claim_token IS NULL AND delivery.owner_worker_id IS NULL AND delivery.lease_until IS NULL "
        "AND EXISTS (SELECT 1 FROM executions AS execution WHERE execution.id = delivery.execution_id "
        "AND execution.execution_metadata->'event_delivery'->>'last_error_code' = 'runtime_unavailable') "
        "RETURNING delivery.execution_id, delivery.next_attempt_at) "
        "UPDATE executions AS execution SET execution_metadata = jsonb_set("
        "execution.execution_metadata, '{event_delivery,next_attempt_at}', "
        "to_jsonb(awakened.next_attempt_at::text), true) "
        "FROM awakened WHERE execution.id = awakened.execution_id"
    )
    # END CUSTOM


def downgrade() -> None:
    """Do not re-park work whose retry has already been permitted or completed."""
