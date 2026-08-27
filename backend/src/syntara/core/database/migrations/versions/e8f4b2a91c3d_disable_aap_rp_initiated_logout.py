"""disable RP-initiated logout on existing AAP identity providers

Revision ID: e8f4b2a91c3d
Revises: c7e4a91b2d03
Create Date: 2026-08-27 00:00:00.000000

Remediates AAP-89344: RP-initiated logout against a shared AAP OAuth2 application
causes django-oauth-toolkit to delete API tokens tied to that application across
all users. Disable the flag on existing AAP IdP records created before the fix.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8f4b2a91c3d"
down_revision: str | Sequence[str] | None = "c7e4a91b2d03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Disable RP-initiated logout on AAP OIDC identity providers."""
    # CUSTOM: data migration — JSONB configuration update not handled by autogenerate
    op.execute(
        """
        UPDATE identity_providers
        SET configuration = jsonb_set(
            configuration,
            '{enable_rp_initiated_logout}',
            'false'::jsonb
        )
        WHERE configuration->>'provider_type' = 'oidc'
          AND configuration->>'idp_type' = 'aap'
          AND COALESCE((configuration->>'enable_rp_initiated_logout')::boolean, false) = true
        """
    )
    # END CUSTOM


def downgrade() -> None:
    """Downgrade schema."""
    # CUSTOM: intentional no-op — re-enabling RP-initiated logout on AAP providers
    # can delete OAuth application API tokens across all users (AAP-89344).
    # END CUSTOM
