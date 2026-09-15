"""Integration tests for IdP group sync with malformed claims.

Verifies that malformed OIDC group claims clear IdP-managed groups
instead of keeping stale memberships from prior logins.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlmodel import select

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.services.idp_group_sync import sync_idp_groups
from syntara.core.models import Group, User
from syntara.core.models.group import user_groups, user_idp_groups
from syntara.core.models.user import AuthType
from syntara.core.models.user_identity import UserIdentity
from syntara.identity_providers.models.identity_provider import IdentityProvider
from syntara.identity_providers.models.identity_provider_configuration import OIDCConfiguration
from syntara.identity_providers.models.idp_group_mapping import IdpGroupMappingEntry

pytestmark = pytest.mark.integration


@pytest.fixture
async def test_user(test_db_session: AsyncSession) -> User:
    """Create a federated user."""
    user = User(
        username=f"testuser-{uuid4().hex[:8]}",
        email=f"test-{uuid4().hex[:8]}@example.com",
        first_name="Test",
        last_name="User",
        is_enabled=True,
        auth_type=AuthType.FEDERATED,
    )
    test_db_session.add(user)
    await test_db_session.flush()
    return user


@pytest.fixture
async def test_group(test_db_session: AsyncSession, test_user: User) -> Group:
    """Create a group."""
    group = Group(
        name=f"test-group-{uuid4().hex[:8]}",
        description="Test group",
        created_by=test_user.id,
    )
    test_db_session.add(group)
    await test_db_session.flush()
    return group


@pytest.fixture
async def users_group(test_db_session: AsyncSession, test_user: User) -> Group:
    """Create the built-in users group required by sync_idp_groups."""
    group = Group(
        name="users",
        description="Built-in users group",
        is_builtin=True,
        created_by=test_user.id,
    )
    test_db_session.add(group)
    await test_db_session.flush()
    return group


@pytest.fixture
async def identity_provider(test_db_session: AsyncSession, test_user: User) -> IdentityProvider:
    """Create an identity provider in the database."""
    provider = IdentityProvider(
        name=f"test-idp-{uuid4().hex[:8]}",
        enabled=True,
        created_by=test_user.id,
        configuration={
            "provider_type": "oidc",
            "issuer_url": "https://idp.example.com",
            "client_id": f"client-{uuid4().hex[:8]}",
            "redirect_uri": "http://localhost:8000/callback",
        },
    )
    test_db_session.add(provider)
    await test_db_session.flush()
    return provider


@pytest.fixture
async def provider_id(identity_provider: IdentityProvider) -> UUID:
    """Identity provider ID."""
    return identity_provider.id


@pytest.fixture
async def test_identity(test_db_session: AsyncSession, test_user: User, provider_id: UUID) -> UserIdentity:
    """Create a user identity."""
    identity = UserIdentity(
        user_id=test_user.id,
        identity_provider_id=provider_id,
        issuer="https://idp.example.com",
        subject=f"sub-{uuid4().hex[:8]}",
    )
    test_db_session.add(identity)
    await test_db_session.flush()
    return identity


@pytest.fixture
async def group_mapping(test_db_session: AsyncSession, provider_id: UUID, test_group: Group) -> IdpGroupMappingEntry:
    """Create a group mapping entry."""
    entry = IdpGroupMappingEntry(
        identity_provider_id=provider_id,
        idp_group_value="admin",
        mapped_group_id=test_group.id,
    )
    test_db_session.add(entry)
    await test_db_session.flush()
    return entry


class TestMalformedClaimClearsGroups:
    """Verify malformed claims clear IdP-managed groups instead of keeping stale memberships."""

    @pytest.mark.asyncio
    async def test_malformed_claim_clears_groups_with_allow_all(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_identity: UserIdentity,
        test_group: Group,
        users_group: Group,
        provider_id: UUID,
        group_mapping: IdpGroupMappingEntry,
    ) -> None:
        """Malformed claim with allow_all_authenticated should clear IdP groups, keep only fallback."""
        config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="groups[*]",
            allow_all_authenticated=True,
        )

        # First login: healthy claim grants test_group
        result = await sync_idp_groups(
            test_db_session,
            test_user,
            test_identity,
            {"groups": ["admin"]},
            config,
        )
        await test_db_session.flush()
        assert result is True

        # Verify test_group and users_group granted
        memberships = await test_db_session.exec(
            select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
        )
        group_ids = set(memberships.all())
        assert test_group.id in group_ids
        assert users_group.id in group_ids

        # Second login: malformed claim (scalar instead of list)
        with patch("syntara.auth.services.idp_group_sync.jmespath.search", side_effect=TypeError("unexpected type")):
            result = await sync_idp_groups(
                test_db_session,
                test_user,
                test_identity,
                {"groups": "admin"},  # Malformed: scalar instead of list
                config,
            )
        await test_db_session.flush()
        assert result is True  # Login still succeeds due to allow_all_authenticated

        # Verify test_group removed, only users_group remains
        memberships = await test_db_session.exec(
            select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
        )
        group_ids = set(memberships.all())
        assert test_group.id not in group_ids, "Stale IdP-managed group should be cleared"
        assert users_group.id in group_ids, "Fallback group should remain"

        # Verify IdP tracking table only has users_group
        idp_tracking = await test_db_session.exec(
            select(user_idp_groups.c.group_id).where(user_idp_groups.c.user_id == test_user.id)
        )
        tracked_ids = set(idp_tracking.all())
        assert tracked_ids == {users_group.id}

    @pytest.mark.asyncio
    async def test_scalar_claim_clears_groups_with_allow_all(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_identity: UserIdentity,
        test_group: Group,
        users_group: Group,
        provider_id: UUID,
        group_mapping: IdpGroupMappingEntry,
    ) -> None:
        """Scalar claim where list expected should clear IdP groups when allow_all_authenticated enabled."""
        config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="groups[*]",
            allow_all_authenticated=True,
        )

        # First login: healthy claim
        result = await sync_idp_groups(
            test_db_session,
            test_user,
            test_identity,
            {"groups": ["admin"]},
            config,
        )
        await test_db_session.flush()
        assert result is True

        # Verify test_group granted
        memberships = await test_db_session.exec(
            select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
        )
        assert test_group.id in set(memberships.all())

        # Second login: scalar claim (extract_idp_group_values detects mismatch)
        result = await sync_idp_groups(
            test_db_session,
            test_user,
            test_identity,
            {"groups": "admin"},  # Scalar where [*] expects list
            config,
        )
        await test_db_session.flush()
        assert result is True

        # Verify test_group removed
        memberships = await test_db_session.exec(
            select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
        )
        group_ids = set(memberships.all())
        assert test_group.id not in group_ids, "Stale group should be cleared on scalar mismatch"
        assert users_group.id in group_ids, "Fallback group should remain"

    @pytest.mark.asyncio
    async def test_malformed_claim_clears_groups_without_allow_all(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_identity: UserIdentity,
        test_group: Group,
        users_group: Group,
        provider_id: UUID,
        group_mapping: IdpGroupMappingEntry,
    ) -> None:
        """Malformed claim without allow_all must clear stale IdP groups and deny login."""
        config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="groups[*]",
            allow_all_authenticated=False,
        )

        # First login: healthy claim grants test_group via mapping
        result = await sync_idp_groups(
            test_db_session,
            test_user,
            test_identity,
            {"groups": ["admin"]},
            config,
        )
        await test_db_session.flush()
        assert result is True

        # Verify test_group granted and tracked as IdP-managed
        memberships = await test_db_session.exec(
            select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
        )
        assert test_group.id in set(memberships.all())

        idp_tracking = await test_db_session.exec(
            select(user_idp_groups.c.group_id).where(user_idp_groups.c.user_id == test_user.id)
        )
        assert test_group.id in set(idp_tracking.all())

        # Second login: malformed claim — JMESPath raises
        with patch("syntara.auth.services.idp_group_sync.jmespath.search", side_effect=TypeError("unexpected type")):
            result = await sync_idp_groups(
                test_db_session,
                test_user,
                test_identity,
                {"groups": "admin"},
                config,
            )
        await test_db_session.flush()
        assert result is False, "Login must be denied when extraction fails without fallback"

        # Critical: stale IdP-managed group must be cleared even though login is denied
        memberships = await test_db_session.exec(
            select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
        )
        group_ids = set(memberships.all())
        assert test_group.id not in group_ids, "Stale IdP-managed group must be cleared on extraction failure"

        # IdP tracking table must be empty for this provider
        idp_tracking = await test_db_session.exec(
            select(user_idp_groups.c.group_id).where(
                user_idp_groups.c.user_id == test_user.id,
                user_idp_groups.c.identity_provider_id == provider_id,
            )
        )
        assert set(idp_tracking.all()) == set(), "IdP tracking must be cleared on extraction failure"

    @pytest.mark.asyncio
    async def test_aap_deny_clears_groups_on_issuer_mismatch(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_identity: UserIdentity,
        test_group: Group,
        users_group: Group,
        provider_id: UUID,
        group_mapping: IdpGroupMappingEntry,
    ) -> None:
        """AAP issuer mismatch must clear stale IdP groups and deny login."""
        admins_group = Group(
            name="admins",
            description="Built-in admins group",
            is_builtin=True,
            created_by=test_user.id,
        )
        test_db_session.add(admins_group)
        await test_db_session.flush()

        config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="groups[*]",
            aap_role_mapping_enabled=True,
            idp_type="aap",
        )

        # First login: healthy claims — matching issuer, valid role, matching group
        result = await sync_idp_groups(
            test_db_session,
            test_user,
            test_identity,
            {
                "iss": "https://idp.example.com",
                "groups": ["admin"],
                "aap_system_role": "system_administrator",
            },
            config,
        )
        await test_db_session.flush()
        assert result is True

        # Verify groups granted
        memberships = await test_db_session.exec(
            select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
        )
        group_ids = set(memberships.all())
        assert test_group.id in group_ids
        assert admins_group.id in group_ids

        idp_tracking = await test_db_session.exec(
            select(user_idp_groups.c.group_id).where(user_idp_groups.c.user_id == test_user.id)
        )
        assert test_group.id in set(idp_tracking.all())

        # Second login: mismatched issuer — AAP role validation fails
        result = await sync_idp_groups(
            test_db_session,
            test_user,
            test_identity,
            {
                "iss": "https://evil-provider.example.com",
                "groups": ["admin"],
                "aap_system_role": "system_administrator",
            },
            config,
        )
        await test_db_session.flush()
        assert result is False, "Login must be denied on AAP issuer mismatch"

        # Stale IdP-managed groups must be cleared
        memberships = await test_db_session.exec(
            select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
        )
        group_ids = set(memberships.all())
        assert test_group.id not in group_ids, "Stale claim-mapped group must be cleared on AAP deny"
        assert admins_group.id not in group_ids, "Stale AAP-resolved group must be cleared on AAP deny"

        # IdP tracking table must be empty for this provider
        idp_tracking = await test_db_session.exec(
            select(user_idp_groups.c.group_id).where(
                user_idp_groups.c.user_id == test_user.id,
                user_idp_groups.c.identity_provider_id == provider_id,
            )
        )
        assert set(idp_tracking.all()) == set(), "IdP tracking must be cleared on AAP deny"

    @pytest.mark.asyncio
    async def test_deny_does_not_wipe_other_provider_groups(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_identity: UserIdentity,
        test_group: Group,
        users_group: Group,
        provider_id: UUID,
        group_mapping: IdpGroupMappingEntry,
    ) -> None:
        """A denied login at IdP B must NOT clear groups from IdP A.

        Provider-scoped clearing ensures cross-provider groups survive.
        """
        other_provider = IdentityProvider(
            name=f"other-idp-{uuid4().hex[:8]}",
            enabled=True,
            created_by=test_user.id,
            configuration={
                "provider_type": "oidc",
                "issuer_url": "https://other-idp.example.com",
                "client_id": f"client-{uuid4().hex[:8]}",
                "redirect_uri": "http://localhost:8000/callback",
            },
        )
        test_db_session.add(other_provider)
        await test_db_session.flush()

        other_group = Group(
            name=f"other-group-{uuid4().hex[:8]}",
            description="Group from other IdP",
            created_by=test_user.id,
        )
        test_db_session.add(other_group)
        await test_db_session.flush()

        other_identity = UserIdentity(
            user_id=test_user.id,
            identity_provider_id=other_provider.id,
            issuer="https://other-idp.example.com",
            subject=f"sub-{uuid4().hex[:8]}",
        )
        test_db_session.add(other_identity)
        await test_db_session.flush()

        other_mapping = IdpGroupMappingEntry(
            identity_provider_id=other_provider.id,
            idp_group_value="devs",
            mapped_group_id=other_group.id,
        )
        test_db_session.add(other_mapping)
        await test_db_session.flush()

        other_config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://other-idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="groups[*]",
        )

        # Login via other_provider (IdP A) — grants other_group
        result = await sync_idp_groups(
            test_db_session,
            test_user,
            other_identity,
            {"groups": ["devs"]},
            other_config,
        )
        await test_db_session.flush()
        assert result is True

        idp_a_tracking = await test_db_session.exec(
            select(user_idp_groups.c.group_id).where(
                user_idp_groups.c.user_id == test_user.id,
                user_idp_groups.c.identity_provider_id == other_provider.id,
            )
        )
        assert other_group.id in set(idp_a_tracking.all())

        # Now deny at IdP B — malformed claim (no prior successful IdP B login)
        config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="groups[*]",
        )
        with patch(
            "syntara.auth.services.idp_group_sync.jmespath.search",
            side_effect=TypeError("unexpected type"),
        ):
            result = await sync_idp_groups(
                test_db_session,
                test_user,
                test_identity,
                {"groups": "admin"},
                config,
            )
        await test_db_session.flush()
        assert result is False

        # IdP B must have no tracked groups (deny cleared any stale ones)
        idp_b_tracking = await test_db_session.exec(
            select(user_idp_groups.c.group_id).where(
                user_idp_groups.c.user_id == test_user.id,
                user_idp_groups.c.identity_provider_id == provider_id,
            )
        )
        assert set(idp_b_tracking.all()) == set(), "IdP B tracking must be empty"

        memberships = await test_db_session.exec(
            select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
        )
        group_ids = set(memberships.all())

        # IdP A's groups must survive the deny at IdP B
        idp_a_tracking = await test_db_session.exec(
            select(user_idp_groups.c.group_id).where(
                user_idp_groups.c.user_id == test_user.id,
                user_idp_groups.c.identity_provider_id == other_provider.id,
            )
        )
        assert other_group.id in set(idp_a_tracking.all()), "IdP A tracking must survive deny at IdP B"
        assert other_group.id in group_ids, "IdP A's group membership must survive deny at IdP B"

    @pytest.mark.asyncio
    async def test_soft_nomatch_does_not_wipe_other_provider_groups(
        self,
        test_db_session: AsyncSession,
        test_user: User,
        test_identity: UserIdentity,
        test_group: Group,
        users_group: Group,
        provider_id: UUID,
        group_mapping: IdpGroupMappingEntry,
    ) -> None:
        """A soft no-match at IdP B (valid token, no mapping hit) must NOT clear IdP A's groups.

        Unlike hard deny (extraction failure), this tests the path where
        extraction succeeds but returns groups that don't match any mappings,
        resulting in has_matched=False.
        """
        other_provider = IdentityProvider(
            name=f"other-idp-{uuid4().hex[:8]}",
            enabled=True,
            created_by=test_user.id,
            configuration={
                "provider_type": "oidc",
                "issuer_url": "https://other-idp.example.com",
                "client_id": f"client-{uuid4().hex[:8]}",
                "redirect_uri": "http://localhost:8000/callback",
            },
        )
        test_db_session.add(other_provider)
        await test_db_session.flush()

        other_group = Group(
            name=f"other-group-{uuid4().hex[:8]}",
            description="Group from other IdP",
            created_by=test_user.id,
        )
        test_db_session.add(other_group)
        await test_db_session.flush()

        other_identity = UserIdentity(
            user_id=test_user.id,
            identity_provider_id=other_provider.id,
            issuer="https://other-idp.example.com",
            subject=f"sub-{uuid4().hex[:8]}",
        )
        test_db_session.add(other_identity)
        await test_db_session.flush()

        other_mapping = IdpGroupMappingEntry(
            identity_provider_id=other_provider.id,
            idp_group_value="devs",
            mapped_group_id=other_group.id,
        )
        test_db_session.add(other_mapping)
        await test_db_session.flush()

        other_config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://other-idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="groups[*]",
        )

        # Login via other_provider (IdP A) — grants other_group
        result = await sync_idp_groups(
            test_db_session,
            test_user,
            other_identity,
            {"groups": ["devs"]},
            other_config,
        )
        await test_db_session.flush()
        assert result is True

        # Verify IdP A's group is tracked
        idp_a_tracking = await test_db_session.exec(
            select(user_idp_groups.c.group_id).where(
                user_idp_groups.c.user_id == test_user.id,
                user_idp_groups.c.identity_provider_id == other_provider.id,
            )
        )
        assert other_group.id in set(idp_a_tracking.all())

        # Login via test provider (IdP B) — valid token but groups don't match any mapping
        config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="groups[*]",
        )
        result = await sync_idp_groups(
            test_db_session,
            test_user,
            test_identity,
            {"groups": ["unknown-group-no-mapping"]},  # Valid extraction, no mapping hit
            config,
        )
        await test_db_session.flush()
        assert result is False, "Soft no-match must deny login"

        # IdP A's groups must survive the soft no-match at IdP B
        idp_a_tracking = await test_db_session.exec(
            select(user_idp_groups.c.group_id).where(
                user_idp_groups.c.user_id == test_user.id,
                user_idp_groups.c.identity_provider_id == other_provider.id,
            )
        )
        assert other_group.id in set(idp_a_tracking.all()), "IdP A tracking must survive soft no-match at IdP B"

        memberships = await test_db_session.exec(
            select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
        )
        group_ids = set(memberships.all())
        assert other_group.id in group_ids, "IdP A's group membership must survive soft no-match at IdP B"


class TestSyncRouterInteraction:
    """Lock the sync_idp_groups ↔ _resolve_and_login_user interaction.

    These tests exercise the full path: sync clears groups → router queries
    other_groups with NOT IN subquery → commit persists the clear.
    A test here would fail if either the empty-set provider clear or the
    deny-path commit were reverted.
    """

    @pytest.mark.asyncio
    async def test_deny_commits_membership_clear_to_db(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
        test_identity: UserIdentity,
        test_group: Group,
        users_group: Group,
        provider_id: UUID,
        identity_provider: IdentityProvider,
        group_mapping: IdpGroupMappingEntry,
    ) -> None:
        """Malformed claim → sync clears → router commits → new session sees empty.

        This is the regression test for the original fail-open bug: sync
        would clear IdP rows, but router rolled back, restoring stale
        memberships.
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        from syntara.auth.exceptions import OIDCCallbackError, OIDCErrorCode
        from syntara.auth.router import _resolve_and_login_user

        config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="groups[*]",
        )

        import datetime

        # First login: healthy claim grants test_group
        result = await sync_idp_groups(
            test_db_session,
            test_user,
            test_identity,
            {"groups": ["admin"]},
            config,
        )
        # Mark user as returning so deny path commits (not rolls back)
        test_user.last_login = datetime.datetime.now(tz=datetime.UTC)
        await test_db_session.commit()
        assert result is True

        # Verify group granted
        memberships = await test_db_session.exec(
            select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
        )
        assert test_group.id in set(memberships.all())

        # Second login via router: malformed claim
        provider_mock = MagicMock(spec=IdentityProvider)
        provider_mock.name = identity_provider.name
        provider_mock.configuration = config

        mock_resolve = AsyncMock(return_value=(test_user, test_identity))

        with (
            patch("syntara.auth.router._resolve_oidc_user", mock_resolve),
            patch(
                "syntara.auth.services.idp_group_sync.jmespath.search",
                side_effect=TypeError("unexpected type"),
            ),
            pytest.raises(OIDCCallbackError) as exc_info,
        ):
            await _resolve_and_login_user(
                test_db_session,
                {"email": test_user.email, "sub": "sub-1"},
                {"groups": "admin"},
                provider_mock,
                None,
            )

        assert exc_info.value.error_code == OIDCErrorCode.NO_GROUP_MATCH

        # Verify on a NEW session that the membership clear was committed
        async with test_db_session_factory() as verify_session:
            memberships = await verify_session.exec(
                select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
            )
            group_ids = set(memberships.all())
            assert test_group.id not in group_ids, "Stale IdP-managed group must be gone after deny-path commit"

            idp_tracking = await verify_session.exec(
                select(user_idp_groups.c.group_id).where(
                    user_idp_groups.c.user_id == test_user.id,
                    user_idp_groups.c.identity_provider_id == provider_id,
                )
            )
            assert set(idp_tracking.all()) == set(), "IdP tracking must be empty after deny-path commit"

    @pytest.mark.asyncio
    async def test_manual_group_admits_user_when_sync_clears_idp_groups(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
        test_identity: UserIdentity,
        test_group: Group,
        users_group: Group,
        provider_id: UUID,
        identity_provider: IdentityProvider,
        group_mapping: IdpGroupMappingEntry,
    ) -> None:
        """A genuine manual group (no tracking row) must admit the user.

        Seeds a prior IdP-managed membership, adds a manual group, then
        triggers a malformed claim.  Asserts that login succeeds (manual
        group admits) AND the stale IdP-managed group is cleared.
        """
        import datetime
        from unittest.mock import AsyncMock, MagicMock, patch

        from syntara.auth.router import _resolve_and_login_user

        config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="groups[*]",
        )

        # First login: healthy claim grants test_group as IdP-managed
        result = await sync_idp_groups(
            test_db_session,
            test_user,
            test_identity,
            {"groups": ["admin"]},
            config,
        )
        assert result is True

        # Mark user as returning (has logged in before)
        test_user.last_login = datetime.datetime.now(tz=datetime.UTC)

        # Create a manually-assigned group (no user_idp_groups tracking row)
        manual_group = Group(
            name=f"manual-group-{uuid4().hex[:8]}",
            description="Manually assigned group",
            created_by=test_user.id,
        )
        test_db_session.add(manual_group)
        await test_db_session.flush()
        await test_db_session.exec(user_groups.insert().values(user_id=test_user.id, group_id=manual_group.id))
        await test_db_session.commit()

        # Verify setup: user has test_group (IdP-managed) + manual_group
        memberships = await test_db_session.exec(
            select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
        )
        setup_ids = set(memberships.all())
        assert test_group.id in setup_ids, "Setup: IdP-managed group must be present"
        assert manual_group.id in setup_ids, "Setup: manual group must be present"

        provider_mock = MagicMock(spec=IdentityProvider)
        provider_mock.name = identity_provider.name
        provider_mock.configuration = config

        mock_resolve = AsyncMock(return_value=(test_user, test_identity))

        # Second login: malformed claim — IdP groups cleared, manual group admits
        with (
            patch("syntara.auth.router._resolve_oidc_user", mock_resolve),
            patch(
                "syntara.auth.services.idp_group_sync.jmespath.search",
                side_effect=TypeError("unexpected type"),
            ),
        ):
            result_user, _, _is_first_login = await _resolve_and_login_user(
                test_db_session,
                {"email": test_user.email, "sub": "sub-1"},
                {"groups": "admin"},
                provider_mock,
                None,
            )

        assert result_user.id == test_user.id, "Manual group must admit user even when sync fails"

        # Commit — in production the OIDC callback handler commits after
        # _resolve_and_login_user returns; here we do it explicitly.
        await test_db_session.commit()

        # Verify stale IdP-managed group is cleared and manual group survives
        async with test_db_session_factory() as verify_session:
            memberships = await verify_session.exec(
                select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
            )
            group_ids = set(memberships.all())
            assert test_group.id not in group_ids, "Stale IdP-managed group must be cleared"
            assert manual_group.id in group_ids, "Manual group must survive"

            idp_tracking = await verify_session.exec(
                select(user_idp_groups.c.group_id).where(
                    user_idp_groups.c.user_id == test_user.id,
                    user_idp_groups.c.identity_provider_id == provider_id,
                )
            )
            assert set(idp_tracking.all()) == set(), "IdP tracking must be empty after malformed claim"

    @pytest.mark.asyncio
    async def test_idp_tracked_group_does_not_satisfy_fallback_via_router(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        test_user: User,
        test_identity: UserIdentity,
        test_group: Group,
        users_group: Group,
        provider_id: UUID,
        identity_provider: IdentityProvider,
        group_mapping: IdpGroupMappingEntry,
    ) -> None:
        """IdP-A tracked group must NOT satisfy the router's manual-group fallback.

        Scenario: user has IdP-A tracked membership, IdP-B denies (malformed
        claim).  The router's NOT IN subquery must exclude the IdP-A tracked
        group so it doesn't pass the 'other groups' check.  Login must fail
        with NO_GROUP_MATCH and IdP-A rows must remain in the DB.

        This test fails if either:
        - provider-scoped clear regresses to session-scoped wipe, OR
        - the notin_(idp_managed_subq) clause is removed from the router.
        """
        from unittest.mock import AsyncMock, MagicMock, patch

        from syntara.auth.exceptions import OIDCCallbackError, OIDCErrorCode
        from syntara.auth.router import _resolve_and_login_user

        other_provider = IdentityProvider(
            name=f"other-idp-{uuid4().hex[:8]}",
            enabled=True,
            created_by=test_user.id,
            configuration={
                "provider_type": "oidc",
                "issuer_url": "https://other-idp.example.com",
                "client_id": f"client-{uuid4().hex[:8]}",
                "redirect_uri": "http://localhost:8000/callback",
            },
        )
        test_db_session.add(other_provider)
        await test_db_session.flush()

        other_group = Group(
            name=f"other-group-{uuid4().hex[:8]}",
            description="Group from other IdP",
            created_by=test_user.id,
        )
        test_db_session.add(other_group)
        await test_db_session.flush()

        other_identity = UserIdentity(
            user_id=test_user.id,
            identity_provider_id=other_provider.id,
            issuer="https://other-idp.example.com",
            subject=f"sub-{uuid4().hex[:8]}",
        )
        test_db_session.add(other_identity)
        await test_db_session.flush()

        other_mapping = IdpGroupMappingEntry(
            identity_provider_id=other_provider.id,
            idp_group_value="devs",
            mapped_group_id=other_group.id,
        )
        test_db_session.add(other_mapping)
        await test_db_session.flush()

        other_config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://other-idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="groups[*]",
        )

        import datetime

        # Login via IdP A — grants other_group
        result = await sync_idp_groups(
            test_db_session,
            test_user,
            other_identity,
            {"groups": ["devs"]},
            other_config,
        )
        # Mark user as returning so deny path commits (not rolls back)
        test_user.last_login = datetime.datetime.now(tz=datetime.UTC)
        await test_db_session.commit()
        assert result is True

        # Verify IdP A's group is tracked
        idp_a_tracking = await test_db_session.exec(
            select(user_idp_groups.c.group_id).where(
                user_idp_groups.c.user_id == test_user.id,
                user_idp_groups.c.identity_provider_id == other_provider.id,
            )
        )
        assert other_group.id in set(idp_a_tracking.all())

        # Now attempt login via IdP B — malformed claim triggers deny
        config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="groups[*]",
        )

        provider_mock = MagicMock(spec=IdentityProvider)
        provider_mock.name = identity_provider.name
        provider_mock.configuration = config

        mock_resolve = AsyncMock(return_value=(test_user, test_identity))

        with (
            patch("syntara.auth.router._resolve_oidc_user", mock_resolve),
            patch(
                "syntara.auth.services.idp_group_sync.jmespath.search",
                side_effect=TypeError("unexpected type"),
            ),
            pytest.raises(OIDCCallbackError) as exc_info,
        ):
            await _resolve_and_login_user(
                test_db_session,
                {"email": test_user.email, "sub": "sub-1"},
                {"groups": "admin"},
                provider_mock,
                None,
            )

        assert exc_info.value.error_code == OIDCErrorCode.NO_GROUP_MATCH

        # Verify IdP-A rows survive (provider-scoped clear only touched IdP B)
        async with test_db_session_factory() as verify_session:
            idp_a_tracking = await verify_session.exec(
                select(user_idp_groups.c.group_id).where(
                    user_idp_groups.c.user_id == test_user.id,
                    user_idp_groups.c.identity_provider_id == other_provider.id,
                )
            )
            assert other_group.id in set(idp_a_tracking.all()), "IdP A tracking must survive denied login at IdP B"

            memberships = await verify_session.exec(
                select(user_groups.c.group_id).where(user_groups.c.user_id == test_user.id)
            )
            group_ids = set(memberships.all())
            assert other_group.id in group_ids, "IdP A's group membership must survive denied login at IdP B"

    @pytest.mark.asyncio
    async def test_first_login_deny_rolls_back_jit_user(
        self,
        test_db_session: AsyncSession,
        test_db_session_factory: async_sessionmaker[AsyncSession],
        users_group: Group,
        identity_provider: IdentityProvider,
        group_mapping: IdpGroupMappingEntry,
    ) -> None:
        """First-login deny must rollback JIT user — no user/identity persisted.

        Exercises the real _resolve_oidc_user path (unmocked auto-create)
        with a brand-new email/sub. After NO_GROUP_MATCH, a fresh session
        must find no User or UserIdentity for that identity.
        """
        from unittest.mock import MagicMock, patch

        from syntara.auth.exceptions import OIDCCallbackError, OIDCErrorCode
        from syntara.auth.router import _resolve_and_login_user

        config = OIDCConfiguration(
            provider_type="oidc",
            issuer_url="https://idp.example.com",
            client_id="client-id",
            client_secret="client-secret",  # noqa: S106
            redirect_uri="http://localhost:8000/callback",
            group_jmespath_expression="groups[*]",
        )

        await test_db_session.commit()

        jit_email = f"jit-{uuid4().hex[:8]}@example.com"
        jit_sub = f"jit-sub-{uuid4().hex[:8]}"
        issuer = str(config.issuer_url)

        provider_mock = MagicMock(spec=IdentityProvider)
        provider_mock.name = identity_provider.name
        provider_mock.id = identity_provider.id
        provider_mock.configuration = config

        with (
            patch(
                "syntara.auth.services.idp_group_sync.jmespath.search",
                side_effect=TypeError("unexpected type"),
            ),
            pytest.raises(OIDCCallbackError) as exc_info,
        ):
            await _resolve_and_login_user(
                test_db_session,
                {"email": jit_email, "sub": jit_sub, "preferred_username": "jituser"},
                {"groups": "admin"},
                provider_mock,
                None,
            )

        assert exc_info.value.error_code == OIDCErrorCode.NO_GROUP_MATCH

        # Verify on a NEW session that the JIT user was NOT persisted
        async with test_db_session_factory() as verify_session:
            from syntara.core.models.user_identity import UserIdentity as UIModel

            user_result = await verify_session.exec(select(User).where(User.email == jit_email))
            assert user_result.first() is None, "JIT user must not be persisted after rollback"

            identity_result = await verify_session.exec(
                select(UIModel).where(
                    UIModel.issuer == issuer,
                    UIModel.subject == jit_sub,
                )
            )
            assert identity_result.first() is None, "JIT identity must not be persisted after rollback"
