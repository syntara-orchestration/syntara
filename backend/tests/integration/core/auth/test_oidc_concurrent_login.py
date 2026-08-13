"""Integration tests for OIDC concurrent login race conditions (AAP-74606).

These tests use real async DB sessions to verify that the session remains usable
after an IntegrityError during concurrent user/identity creation. Before the fix,
a full ``db.rollback()`` disrupts the async greenlet context, causing
``MissingGreenlet`` on subsequent queries.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.router import (
    _auto_create_user,
    _create_identity_with_race_handling,
    _resolve_oidc_user,
)
from syntara.auth.services.oidc_service import OIDCError
from syntara.core.models import User
from syntara.core.models.user import AuthType
from syntara.core.models.user_identity import UserIdentity
from syntara.identity_providers.models.identity_provider import IdentityProvider
from syntara.users.services.user_identity_service import UserIdentityService

pytestmark = pytest.mark.integration


def _make_idp(user_id: UUID, *, issuer: str = "https://idp.example.com") -> IdentityProvider:
    """Build an IdentityProvider ORM object (not persisted)."""
    return IdentityProvider(
        name=f"test-idp-{uuid4().hex[:8]}",
        enabled=True,
        created_by=user_id,
        configuration={
            "provider_type": "oidc",
            "issuer_url": issuer,
            "client_id": f"client-{uuid4().hex[:8]}",
            "redirect_uri": "https://app.example.com/callback",
        },
    )


@pytest.fixture
async def seed_user(test_db_session: AsyncSession) -> User:
    """Create a federated user in the DB."""
    user = User(
        username=f"oidc-{uuid4().hex[:8]}",
        email=f"oidc-{uuid4().hex[:8]}@example.com",
        first_name="OIDC",
        last_name="Test User",
        is_enabled=True,
        auth_type=AuthType.FEDERATED,
    )
    test_db_session.add(user)
    await test_db_session.flush()
    return user


@pytest.fixture
async def seed_idp(test_db_session: AsyncSession, seed_user: User) -> IdentityProvider:
    """Create an identity provider in the DB."""
    idp = _make_idp(seed_user.id)
    test_db_session.add(idp)
    await test_db_session.flush()
    return idp


class TestAutoCreateUserSessionSurvival:
    """Verify that the session stays usable after IntegrityError in _auto_create_user."""

    @pytest.mark.asyncio
    async def test_session_usable_after_integrity_error(self, test_db_session: AsyncSession, seed_user: User) -> None:
        """After _auto_create_user raises OIDCError, the same session should still work.

        Before the fix (full db.rollback), this crashes with MissingGreenlet.
        """
        email = seed_user.email
        claims: dict[str, str | None] = {
            "sub": "duplicate-sub",
            "email": email,
            "name": "Duplicate",
            "preferred_username": seed_user.username,
        }

        with pytest.raises(OIDCError):
            await _auto_create_user(test_db_session, claims, "TestIDP", email=email)

        # This query should succeed if the session is intact.
        # With the old db.rollback() it crashes: MissingGreenlet.
        from sqlmodel import select

        result = await test_db_session.exec(select(User).where(User.id == seed_user.id))
        reloaded = result.one_or_none()
        assert reloaded is not None
        assert reloaded.id == seed_user.id


class TestCreateIdentitySessionSurvival:
    """Verify session survival after IntegrityError in _create_identity_with_race_handling."""

    @pytest.mark.asyncio
    async def test_returns_existing_after_race(
        self,
        test_db_session: AsyncSession,
        seed_user: User,
        seed_idp: IdentityProvider,
    ) -> None:
        """When identity creation loses a race, the function should return the winner's data.

        Before the fix, the retry query after db.rollback() crashes with MissingGreenlet.
        """
        issuer = seed_idp.configuration.issuer_url
        sub = f"sub-{uuid4().hex[:8]}"

        # Pre-insert the "winner" identity
        winner_identity = UserIdentity(
            user_id=seed_user.id,
            identity_provider_id=seed_idp.id,
            issuer=issuer,
            subject=sub,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        test_db_session.add(winner_identity)
        await test_db_session.flush()

        identity_service = UserIdentityService(test_db_session)

        # Now call the function — it will hit IntegrityError on create, then look up the winner.
        result_user, result_identity = await _create_identity_with_race_handling(
            test_db_session, identity_service, seed_user, seed_idp.id, str(issuer), sub
        )

        assert result_identity.subject == sub
        assert result_user.id == seed_user.id


class TestResolveOidcUserConcurrentCreation:
    """Verify _resolve_oidc_user handles concurrent creation cleanly."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_after_race(
        self,
        test_db_session: AsyncSession,
        seed_user: User,
        seed_idp: IdentityProvider,
    ) -> None:
        """When a concurrent user creation race happens, _resolve_oidc_user retries and succeeds.

        Before the fix, the retry crashes with MissingGreenlet because the session
        was corrupted by the full rollback.
        """
        sub = f"sub-{uuid4().hex[:8]}"
        claims: dict[str, str | None] = {
            "sub": sub,
            "email": f"concurrent-{uuid4().hex[:8]}@example.com",
            "name": "Concurrent User",
            "preferred_username": f"concurrent-{uuid4().hex[:8]}",
        }

        user, identity = await _resolve_oidc_user(test_db_session, claims, seed_idp)

        assert user is not None
        assert identity is not None
        assert identity.subject == sub

    @pytest.mark.asyncio
    async def test_loser_finds_winner_identity_on_retry(
        self,
        test_db_session: AsyncSession,
        seed_user: User,
        seed_idp: IdentityProvider,
    ) -> None:
        """Simulate a loser whose user creation fails because winner already created user+identity.

        The retry should re-run the full resolution: find the winner's identity
        at Step 1 and return it instead of failing.
        """
        issuer = seed_idp.configuration.issuer_url
        sub = f"sub-{uuid4().hex[:8]}"
        email = f"shared-{uuid4().hex[:8]}@example.com"

        # Simulate the winner: create user + identity with the same (issuer, sub)
        winner = User(
            username=f"winner-{uuid4().hex[:8]}",
            email=email,
            first_name="Winner",
            is_enabled=True,
            auth_type=AuthType.FEDERATED,
        )
        test_db_session.add(winner)
        await test_db_session.flush()
        winner_identity = UserIdentity(
            user_id=winner.id,
            identity_provider_id=seed_idp.id,
            issuer=issuer,
            subject=sub,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        test_db_session.add(winner_identity)
        await test_db_session.flush()

        # Now the loser calls _resolve_oidc_user with the same sub and email.
        # Step 1 finds the winner's identity and returns immediately.
        claims: dict[str, str | None] = {
            "sub": sub,
            "email": email,
            "name": "Loser",
            "preferred_username": f"loser-{uuid4().hex[:8]}",
        }

        user, identity = await _resolve_oidc_user(test_db_session, claims, seed_idp)

        assert user.id == winner.id
        assert identity.subject == sub
