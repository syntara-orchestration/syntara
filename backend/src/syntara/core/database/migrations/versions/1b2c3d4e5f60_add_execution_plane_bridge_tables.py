"""Persist AO-owned EP activity bindings and callback events.

Revision ID: 1b2c3d4e5f60
Revises: 8fe7495a14dc
Create Date: 2026-10-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "1b2c3d4e5f60"
down_revision: str | Sequence[str] | None = "8fe7495a14dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create AO's encrypted binding table and durable callback inbox."""
    op.create_table(
        "execution_plane_activity_bindings",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("client_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("temporal_workflow_id", sa.String(length=255), nullable=False),
        sa.Column("temporal_run_id", sa.String(length=255), nullable=False),
        sa.Column("temporal_activity_id", sa.String(length=255), nullable=False),
        sa.Column("activity_attempt", sa.Integer(), nullable=False),
        sa.Column("task_token_ciphertext", sa.Text(), nullable=False),
        sa.Column("request_payload_ciphertext", sa.Text(), nullable=False),
        sa.Column("work_item_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_status_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("request_id", name="uq_ep_activity_bindings_request_id"),
    )
    op.create_index(
        "ix_ep_activity_bindings_status_updated",
        "execution_plane_activity_bindings",
        ["status", "updated_at"],
    )
    op.create_table(
        "execution_plane_completion_inbox",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.String(length=128), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("work_item_id", sa.UUID(), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("state_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result", JSONB(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "client_id",
            "project_id",
            "request_id",
            "state_revision",
            name="uq_ep_completion_inbox_request_revision",
        ),
    )
    op.create_index(
        "ix_ep_completion_inbox_delivery",
        "execution_plane_completion_inbox",
        ["processed_at", "next_attempt_at", "lease_expires_at"],
    )


def downgrade() -> None:
    """Drop bridge state tables."""
    op.drop_index("ix_ep_completion_inbox_delivery", table_name="execution_plane_completion_inbox")
    op.drop_table("execution_plane_completion_inbox")
    op.drop_index("ix_ep_activity_bindings_status_updated", table_name="execution_plane_activity_bindings")
    op.drop_table("execution_plane_activity_bindings")
