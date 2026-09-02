"""user and group hard deletes

Convert users and groups from soft delete to hard delete per the
"Hard Deletes Only" decision record.

Strategy:
- Purge soft-deleted rows (role assignments cleaned first to avoid FK violations).
- Change FK ondelete rules: user_token_configs/token_usage_records → CASCADE,
  groups.created_by → SET NULL.
- Drop deleted_at / deleted_by columns from both tables.
- Convert partial unique indexes to standard unique constraints.

Revision ID: c4a7e1f93d21
Revises: f1b3c7d9e2a4
Create Date: 2026-09-01 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a7e1f93d21"
down_revision: str | Sequence[str] | None = "f1b3c7d9e2a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove soft-deleted rows, change FK rules, drop deleted_at/deleted_by columns."""
    # ── Phase 1: Purge soft-deleted data ──────────────────────────────────
    #
    # Order matters: clean up child references before deleting parent rows.

    # CUSTOM: Clean role assignments pointing at soft-deleted groups.
    op.execute(
        sa.text("DELETE FROM role_assignments WHERE group_id IN (SELECT id FROM groups WHERE deleted_at IS NOT NULL)")
    )

    # CUSTOM: Clean role assignments pointing at soft-deleted users (via principals).
    op.execute(
        sa.text(
            "DELETE FROM role_assignments WHERE principal_id IN (SELECT id FROM users WHERE deleted_at IS NOT NULL)"
        )
    )

    # CUSTOM: Clean user_token_configs for soft-deleted users.
    op.execute(
        sa.text("DELETE FROM user_token_configs WHERE user_id IN (SELECT id FROM users WHERE deleted_at IS NOT NULL)")
    )

    # CUSTOM: Clean token_usage_records for soft-deleted users.
    op.execute(
        sa.text("DELETE FROM token_usage_records WHERE user_id IN (SELECT id FROM users WHERE deleted_at IS NOT NULL)")
    )

    # CUSTOM: Null out groups.created_by referencing soft-deleted users.
    op.execute(
        sa.text(
            "UPDATE groups SET created_by = NULL "
            "WHERE created_by IN (SELECT id FROM users WHERE deleted_at IS NOT NULL)"
        )
    )

    # CUSTOM: Purge soft-deleted groups.
    # user_groups, user_idp_groups, idp_group_mapping_entries,
    # approval_approver_groups all CASCADE automatically.
    op.execute(sa.text("DELETE FROM groups WHERE deleted_at IS NOT NULL"))

    # CUSTOM: Null out self-referential deleted_by FK before purging users.
    op.execute(sa.text("UPDATE users SET deleted_by = NULL WHERE deleted_at IS NOT NULL"))

    # CUSTOM: Null out groups.deleted_by before dropping column (all values, not just soft-deleted).
    op.execute(sa.text("UPDATE groups SET deleted_by = NULL WHERE deleted_by IS NOT NULL"))

    # CUSTOM: Purge soft-deleted users.
    # user_groups, user_idp_groups, user_identities, refresh_sessions,
    # approval_approver_users all CASCADE automatically.
    op.execute(sa.text("DELETE FROM users WHERE deleted_at IS NOT NULL"))
    # END CUSTOM

    # ── Phase 2: Change FK ondelete rules ─────────────────────────────────

    # -- user_token_configs.user_id: NO ACTION → CASCADE --
    op.drop_constraint("user_token_configs_user_id_fkey", "user_token_configs", type_="foreignkey")
    op.create_foreign_key(
        "user_token_configs_user_id_fkey",
        "user_token_configs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # -- token_usage_records.user_id: NO ACTION → CASCADE --
    op.drop_constraint("token_usage_records_user_id_fkey", "token_usage_records", type_="foreignkey")
    op.create_foreign_key(
        "token_usage_records_user_id_fkey",
        "token_usage_records",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # -- groups.created_by: NO ACTION → SET NULL --
    op.drop_constraint("groups_created_by_fkey", "groups", type_="foreignkey")
    op.create_foreign_key(
        "groups_created_by_fkey",
        "groups",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )

    # ── Phase 3: Drop deleted_by FK constraints ──────────────────────────
    op.drop_constraint("groups_deleted_by_fkey", "groups", type_="foreignkey")
    op.drop_constraint("users_deleted_by_fkey", "users", type_="foreignkey")

    # ── Phase 4: Convert partial unique indexes to standard ──────────────

    # -- users: username --
    op.drop_index("ix_users_username_unique", table_name="users")
    op.create_unique_constraint("uq_users_username", "users", ["username"])

    # -- users: email (keep WHERE email IS NOT NULL, drop deleted_at condition) --
    op.drop_index("ix_users_email_unique", table_name="users")
    op.create_index(
        "ix_users_email_unique",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )

    # -- groups: name --
    op.drop_index("ix_groups_name_unique", table_name="groups")
    op.create_unique_constraint("uq_groups_name", "groups", ["name"])

    # ── Phase 5: Drop indexes on deleted_at/deleted_by ───────────────────
    op.drop_index(op.f("ix_users_deleted_at"), table_name="users")
    op.drop_index(op.f("ix_users_deleted_by"), table_name="users")
    op.drop_index(op.f("ix_groups_deleted_at"), table_name="groups")
    op.drop_index(op.f("ix_groups_deleted_by"), table_name="groups")

    # ── Phase 6: Drop deleted_at/deleted_by columns ──────────────────────
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "deleted_by")
    op.drop_column("groups", "deleted_at")
    op.drop_column("groups", "deleted_by")


def downgrade() -> None:
    """Restore soft-delete columns and original FK constraints.

    WARNING: This restores schema only. Rows purged by upgrade() (previously
    soft-deleted users/groups) are NOT recoverable.
    """
    # Re-add deleted_at/deleted_by columns
    op.add_column("groups", sa.Column("deleted_by", sa.UUID(), nullable=True))
    op.add_column("groups", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deleted_by", sa.UUID(), nullable=True))
    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))

    # Recreate indexes on restored columns
    op.create_index(op.f("ix_groups_deleted_at"), "groups", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_groups_deleted_by"), "groups", ["deleted_by"], unique=False)
    op.create_index(op.f("ix_users_deleted_at"), "users", ["deleted_at"], unique=False)
    op.create_index(op.f("ix_users_deleted_by"), "users", ["deleted_by"], unique=False)

    # Restore partial unique indexes
    op.drop_constraint("uq_groups_name", "groups", type_="unique")
    op.create_index(
        "ix_groups_name_unique",
        "groups",
        ["name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.drop_index("ix_users_email_unique", table_name="users")
    op.create_index(
        "ix_users_email_unique",
        "users",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL AND deleted_at IS NULL"),
    )

    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.create_index(
        "ix_users_username_unique",
        "users",
        ["username"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # Restore deleted_by FK constraints
    op.create_foreign_key("users_deleted_by_fkey", "users", "users", ["deleted_by"], ["id"])
    op.create_foreign_key("groups_deleted_by_fkey", "groups", "users", ["deleted_by"], ["id"])

    # Restore groups.created_by FK (NO ACTION)
    op.drop_constraint("groups_created_by_fkey", "groups", type_="foreignkey")
    op.create_foreign_key("groups_created_by_fkey", "groups", "users", ["created_by"], ["id"])

    # Restore token_usage_records.user_id FK (NO ACTION)
    op.drop_constraint("token_usage_records_user_id_fkey", "token_usage_records", type_="foreignkey")
    op.create_foreign_key("token_usage_records_user_id_fkey", "token_usage_records", "users", ["user_id"], ["id"])

    # Restore user_token_configs.user_id FK (NO ACTION)
    op.drop_constraint("user_token_configs_user_id_fkey", "user_token_configs", type_="foreignkey")
    op.create_foreign_key("user_token_configs_user_id_fkey", "user_token_configs", "users", ["user_id"], ["id"])
