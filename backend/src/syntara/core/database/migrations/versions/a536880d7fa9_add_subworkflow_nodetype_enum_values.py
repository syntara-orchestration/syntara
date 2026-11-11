"""add sub_workflow and subworkflow_trigger to nodetype enum

Revision ID: a536880d7fa9
Revises: d5b8c2f04e71
Create Date: 2026-10-28

The Python ``NodeType`` enum gained ``SUB_WORKFLOW`` ("sub_workflow") and
``SUBWORKFLOW_TRIGGER`` ("subworkflow_trigger"), but
the PostgreSQL ``nodetype`` enum created in the baseline migration
(``b69ef9067e66``) was never extended. Inserting an ``ActivityExecution`` whose
``node_type`` is either value fails with ``invalid input value for enum
nodetype``. That abort happens inside the activity-monitoring initialization
(``_create_all_activities_upfront``) before the monitor processes the
``WorkflowExecutionStarted`` event, so sub-workflow executions never transition
out of PENDING even though they complete in Temporal.

This migration adds only the two missing labels.

``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction block on
PostgreSQL < 12, and on PostgreSQL >= 12 a value added inside a transaction is
not usable until that transaction commits. Both ``ADD VALUE`` statements are
therefore issued inside an autocommit block so the migration is safe on every
supported PostgreSQL version and the new labels are usable by the application
immediately afterwards.

Autocommit does not make the two statements atomic: they commit independently,
so a failure after the first ``ADD VALUE`` and before the second would leave
``sub_workflow`` committed and ``subworkflow_trigger`` missing. That partial
state is safe to recover from by re-running the migration -- ``IF NOT EXISTS``
turns the already-added value into a no-op and the remaining value is then
added. ``IF NOT EXISTS`` likewise makes the whole migration a no-op on a
database that already contains both values (for example one bootstrapped from
current model metadata).

Downgrade is an intentional no-op: PostgreSQL cannot remove a value from an
enum type. The only alternatives are destructive -- recreate the type and
rewrite every dependent column -- and would fail or lose data if any row
already uses the value. The extra labels are inert unless a row references
them, so they are left in place.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a536880d7fa9"
down_revision: str | Sequence[str] | None = "d5b8c2f04e71"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the sub_workflow and subworkflow_trigger labels to the nodetype enum."""
    # ADD VALUE must run outside the migration's transaction (see module docstring).
    # The statements commit independently; IF NOT EXISTS keeps the migration
    # retryable if it fails between the two.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE nodetype ADD VALUE IF NOT EXISTS 'sub_workflow'")
        op.execute("ALTER TYPE nodetype ADD VALUE IF NOT EXISTS 'subworkflow_trigger'")


def downgrade() -> None:
    """Intentionally do nothing: PostgreSQL cannot drop enum values (see module docstring)."""
