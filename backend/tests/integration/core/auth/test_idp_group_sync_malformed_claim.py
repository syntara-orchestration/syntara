"""Integration tests for IdP group sync with malformed claims.

Verifies that malformed OIDC group claims clear IdP-managed groups
instead of keeping stale memberships from prior logins.
"""

from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.auth.services.idp_group_sync import sync_idp_groups
from syntara.core.models import Group, User
from syntara.core.models.group import user_groups, user_idp_groups
from syntara.core.models.user import AuthType
from syntara.core.models.user_identity import UserIdentity
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
async def users_group(test_db_session: AsyncSession) -> Group:
    """Load the built-in users group."""
    result = await test_db_session.exec(
        select(Group).where(
            col(Group.name) == "users",
            col(Group.is_builtin) == True,  # noqa: E712
            Group.deleted_at.is_(None),  # type: ignore[union-attr]
        )
    )
    return result.one()


@pytest.fixture
async def provider_id() -> UUID:
    """Identity provider ID."""
    return uuid4()


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
        nexus_group_id=test_group.id,
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
