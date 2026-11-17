"""plugins migrate script node credentials

Revision ID: a3f7b8c9d0e1
Revises: e2f6a8c1d4b7
Create Date: 2026-11-17 08:30:00.000000

"""

from __future__ import annotations

from typing import TYPE_CHECKING

from alembic import op

from syntara.execution_plane.database.migrations import (
    downgrade_workflow_credential_bindings,
    migrate_workflow_credential_bindings,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "a3f7b8c9d0e1"
down_revision: str | Sequence[str] | None = "e2f6a8c1d4b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove temporary Script credentials."""
    migrate_workflow_credential_bindings(op.get_bind(), node_types=("script",))


def downgrade() -> None:
    """Restore the first bound credential as the legacy credential field."""
    downgrade_workflow_credential_bindings(op.get_bind(), node_types=("script",))
