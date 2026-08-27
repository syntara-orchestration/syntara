"""disable RP-initiated logout on existing AAP OIDC identity providers

Data migration remediating existing AAP identity providers. Providers created by
the push-button setup were persisted with ``enable_rp_initiated_logout = true`` in
their JSONB ``configuration``. Because that setup registers a single OAuth2
application shared by every user, RP-initiated logout makes AAP
(django-oauth-toolkit) delete every API token tied to the shared application on
logout — across all users, not just the one logging out. This migration flips
the flag to ``false`` on already-created AAP providers so existing deployments
are remediated, matching the corrected setup default.

Only AAP-type OIDC providers are touched; custom OIDC providers keep whatever an
admin configured.

Revision ID: f2a4c6d8e1b3
Revises: a986f158ce16
Create Date: 2026-08-27 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a4c6d8e1b3"
down_revision: str | Sequence[str] | None = "a986f158ce16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # CUSTOM: data-only remediation, not detected by autogenerate.
    # Flip enable_rp_initiated_logout -> false for AAP OIDC providers that still
    # have it enabled, so logging out of AO no longer triggers AAP's token wipe.
    op.execute(
        """
        UPDATE identity_providers
        SET configuration = jsonb_set(
            configuration, '{enable_rp_initiated_logout}', 'false'::jsonb, false
        )
        WHERE configuration->>'provider_type' = 'oidc'
          AND configuration->>'idp_type' = 'aap'
          AND configuration->>'enable_rp_initiated_logout' = 'true'
        """
    )
    # END CUSTOM


def downgrade() -> None:
    """Downgrade schema."""
    # CUSTOM: intentional no-op. Re-enabling RP-initiated logout on the shared AAP
    # application would reintroduce the token-wipe vulnerability, and the
    # original per-row values are not recoverable. Admins who want single sign-out can
    # re-enable it per identity provider.
    # END CUSTOM
