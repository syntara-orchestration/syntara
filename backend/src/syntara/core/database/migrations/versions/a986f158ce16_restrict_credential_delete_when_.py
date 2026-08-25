"""restrict credential delete when integration references it

Revision ID: a986f158ce16
Revises: c7e4a91b2d03
Create Date: 2026-08-21 12:26:10.309857

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a986f158ce16"
down_revision: str | Sequence[str] | None = "c7e4a91b2d03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # CUSTOM: ondelete change not detected by autogenerate.
    # The app-level guard in CredentialService.delete_credential blocks deletes
    # while integrations reference the credential, but the previous
    # ON DELETE SET NULL constraint left a TOCTOU race: an integration attached
    # to the credential between the app-level check and the delete would still
    # be silently nulled by the database cascade. RESTRICT closes that gap by
    # having the database itself reject the delete.
    op.drop_constraint(
        "integrations_management_credential_id_fkey",
        "integrations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "integrations_management_credential_id_fkey",
        "integrations",
        "credentials",
        ["management_credential_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    # END CUSTOM


def downgrade() -> None:
    """Downgrade schema."""
    # CUSTOM: revert to the original ON DELETE SET NULL behavior.
    op.drop_constraint(
        "integrations_management_credential_id_fkey",
        "integrations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "integrations_management_credential_id_fkey",
        "integrations",
        "credentials",
        ["management_credential_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # END CUSTOM
