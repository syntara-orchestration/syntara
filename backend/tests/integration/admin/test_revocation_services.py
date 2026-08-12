"""Unit tests for admin revocation service functions."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from syntara.admin.services import (
    find_idp_by_name,
    find_user_by_username,
    get_revocation_timestamp,
    revoke_idp_sessions,
    revoke_user_sessions,
    set_global_revocation_timestamp,
)
from syntara.auth.models.global_revocation_timestamp import GlobalRevocationTimestamp

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


pytestmark = pytest.mark.asyncio


class TestSetGlobalRevocationTimestamp:
    """Tests for set_global_revocation_timestamp."""

    async def test_updates_existing_row(
        self,
        test_db_session: AsyncSession,
    ) -> None:
        old_time = datetime(2024, 1, 1, tzinfo=UTC)
        test_db_session.add(GlobalRevocationTimestamp(id=1, revoked_before=old_time, updated_at=old_time))
        await test_db_session.commit()

        with patch("syntara.admin.services.AuditEventDispatcher"):
            result = await set_global_revocation_timestamp(test_db_session, actor_username="admin", actor_source="api")
            await test_db_session.commit()

        assert result > old_time
        row = await get_revocation_timestamp(test_db_session)
        assert row is not None
        assert row.revoked_before == result
        assert row.updated_by == "admin"

    async def test_inserts_row_when_none_exists(
        self,
        test_db_session: AsyncSession,
    ) -> None:
        with patch("syntara.admin.services.AuditEventDispatcher"):
            result = await set_global_revocation_timestamp(test_db_session, actor_username="admin", actor_source="cli")
            await test_db_session.commit()

        row = await get_revocation_timestamp(test_db_session)
        assert row is not None
        assert row.revoked_before == result
        assert row.updated_by == "admin"

    async def test_dispatches_global_revocation_audit_event(
        self,
        test_db_session: AsyncSession,
    ) -> None:
        with patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher:
            await set_global_revocation_timestamp(test_db_session, actor_username="testadmin", actor_source="api")

        mock_dispatcher.dispatch.assert_called_once()
        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.actor_username == "testadmin"
        assert event.actor_source == "api"
        assert event.revocation_timestamp is not None

    async def test_audit_dispatch_failure_does_not_raise(
        self,
        test_db_session: AsyncSession,
    ) -> None:
        with patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher:
            mock_dispatcher.dispatch.side_effect = RuntimeError("audit down")
            result = await set_global_revocation_timestamp(test_db_session, actor_username="admin", actor_source="api")

        assert isinstance(result, datetime)

    async def test_returns_utc_datetime(
        self,
        test_db_session: AsyncSession,
    ) -> None:
        with patch("syntara.admin.services.AuditEventDispatcher"):
            result = await set_global_revocation_timestamp(test_db_session, actor_username="admin", actor_source="api")

        assert result.tzinfo is UTC


class TestGetRevocationTimestamp:
    """Tests for get_revocation_timestamp."""

    async def test_returns_none_when_no_row(
        self,
        test_db_session: AsyncSession,
    ) -> None:
        result = await get_revocation_timestamp(test_db_session)
        assert result is None

    async def test_returns_row_when_set(
        self,
        test_db_session: AsyncSession,
    ) -> None:
        now = datetime.now(UTC)
        test_db_session.add(GlobalRevocationTimestamp(id=1, revoked_before=now, updated_at=now))
        await test_db_session.commit()

        result = await get_revocation_timestamp(test_db_session)
        assert result is not None
        assert result.id == 1


class TestFindUserByUsername:
    """Tests for find_user_by_username."""

    async def test_returns_user_by_username(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        result = await find_user_by_username(test_db_session, test_user.username)
        assert result is not None
        assert result.id == test_user.id

    async def test_case_insensitive_lookup(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        result = await find_user_by_username(test_db_session, test_user.username.upper())
        assert result is not None
        assert result.id == test_user.id

    async def test_returns_none_for_nonexistent_user(
        self,
        test_db_session: AsyncSession,
    ) -> None:
        result = await find_user_by_username(test_db_session, "no_such_user_xyz")
        assert result is None

    async def test_excludes_soft_deleted_users(
        self,
        test_db_session: AsyncSession,
        user_factory,
    ) -> None:
        user = await user_factory(username="deleteduser", email="deleted@test.com")
        user.deleted_at = datetime.now(UTC)
        test_db_session.add(user)
        await test_db_session.commit()

        result = await find_user_by_username(test_db_session, "deleteduser")
        assert result is None


class TestRevokeUserSessions:
    """Tests for revoke_user_sessions."""

    async def test_returns_revoked_count(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        with patch("syntara.admin.services.create_session_store") as mock_create:
            mock_store = AsyncMock()
            mock_store.revoke_all_for_user.return_value = 3
            mock_store.increment_token_version.return_value = 2
            mock_create.return_value = mock_store

            with patch("syntara.admin.services.AuditEventDispatcher"):
                count = await revoke_user_sessions(
                    test_db_session,
                    test_user,
                    actor_username="admin",
                    actor_source="api",
                )

        assert count == 3
        mock_store.revoke_all_for_user.assert_awaited_once_with(test_user.id)
        mock_store.increment_token_version.assert_awaited_once_with(test_user.id)

    async def test_dispatches_session_revocation_event(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        with patch("syntara.admin.services.create_session_store") as mock_create:
            mock_store = AsyncMock()
            mock_store.revoke_all_for_user.return_value = 2
            mock_store.increment_token_version.return_value = 1
            mock_create.return_value = mock_store

            with patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher:
                await revoke_user_sessions(
                    test_db_session,
                    test_user,
                    actor_username="revoker",
                    actor_source="cli",
                )

        mock_dispatcher.dispatch.assert_called_once()
        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.target_type == "user"
        assert event.target_identifier == test_user.username
        assert event.sessions_revoked == 2
        assert event.actor_username == "revoker"
        assert event.actor_source == "cli"

    async def test_returns_zero_when_no_sessions(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        with patch("syntara.admin.services.create_session_store") as mock_create:
            mock_store = AsyncMock()
            mock_store.revoke_all_for_user.return_value = 0
            mock_store.increment_token_version.return_value = 1
            mock_create.return_value = mock_store

            with patch("syntara.admin.services.AuditEventDispatcher"):
                count = await revoke_user_sessions(
                    test_db_session,
                    test_user,
                    actor_username="admin",
                    actor_source="api",
                )

        assert count == 0

    async def test_audit_dispatch_failure_does_not_raise(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        with patch("syntara.admin.services.create_session_store") as mock_create:
            mock_store = AsyncMock()
            mock_store.revoke_all_for_user.return_value = 1
            mock_store.increment_token_version.return_value = 1
            mock_create.return_value = mock_store

            with patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher:
                mock_dispatcher.dispatch.side_effect = RuntimeError("audit broken")
                count = await revoke_user_sessions(
                    test_db_session,
                    test_user,
                    actor_username="admin",
                    actor_source="api",
                )

        assert count == 1


class TestFindIdpByName:
    """Tests for find_idp_by_name."""

    async def test_returns_provider_by_name(
        self,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        from syntara.identity_providers.models.identity_provider import IdentityProvider

        provider = IdentityProvider(
            id=uuid4(),
            name="Test OIDC",
            created_by=test_user.id,
            configuration={
                "provider_type": "oidc",
                "issuer_url": "https://example.com",
                "client_id": "c",
                "client_secret": "s",
                "redirect_uri": "http://localhost/cb",
            },
        )
        test_db_session.add(provider)
        await test_db_session.commit()

        result = await find_idp_by_name(test_db_session, "Test OIDC")
        assert result is not None
        assert result.id == provider.id

    async def test_returns_none_for_nonexistent_provider(
        self,
        test_db_session: AsyncSession,
    ) -> None:
        result = await find_idp_by_name(test_db_session, "No Such Provider")
        assert result is None


class TestRevokeIdpSessions:
    """Tests for revoke_idp_sessions."""

    async def test_returns_revoked_count(
        self,
        test_db_session: AsyncSession,
    ) -> None:
        idp_id = uuid4()
        with patch("syntara.admin.services.create_session_store") as mock_create:
            mock_store = AsyncMock()
            mock_store.revoke_by_idp.return_value = 5
            mock_create.return_value = mock_store

            with patch("syntara.admin.services.AuditEventDispatcher"):
                count = await revoke_idp_sessions(
                    test_db_session,
                    idp_id,
                    idp_name="MyIdP",
                    actor_username="admin",
                    actor_source="api",
                )

        assert count == 5
        mock_store.revoke_by_idp.assert_awaited_once_with(str(idp_id))

    async def test_dispatches_session_revocation_event(
        self,
        test_db_session: AsyncSession,
    ) -> None:
        idp_id = uuid4()
        with patch("syntara.admin.services.create_session_store") as mock_create:
            mock_store = AsyncMock()
            mock_store.revoke_by_idp.return_value = 4
            mock_create.return_value = mock_store

            with patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher:
                await revoke_idp_sessions(
                    test_db_session,
                    idp_id,
                    idp_name="AuditIdP",
                    actor_username="adminuser",
                    actor_source="cli",
                )

        mock_dispatcher.dispatch.assert_called_once()
        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.target_type == "idp"
        assert event.target_identifier == "AuditIdP"
        assert event.sessions_revoked == 4
        assert event.actor_username == "adminuser"
        assert event.actor_source == "cli"

    async def test_returns_zero_when_no_sessions(
        self,
        test_db_session: AsyncSession,
    ) -> None:
        idp_id = uuid4()
        with patch("syntara.admin.services.create_session_store") as mock_create:
            mock_store = AsyncMock()
            mock_store.revoke_by_idp.return_value = 0
            mock_create.return_value = mock_store

            with patch("syntara.admin.services.AuditEventDispatcher"):
                count = await revoke_idp_sessions(
                    test_db_session,
                    idp_id,
                    idp_name="EmptyIdP",
                    actor_username="admin",
                    actor_source="api",
                )

        assert count == 0

    async def test_audit_dispatch_failure_does_not_raise(
        self,
        test_db_session: AsyncSession,
    ) -> None:
        idp_id = uuid4()
        with patch("syntara.admin.services.create_session_store") as mock_create:
            mock_store = AsyncMock()
            mock_store.revoke_by_idp.return_value = 2
            mock_create.return_value = mock_store

            with patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher:
                mock_dispatcher.dispatch.side_effect = RuntimeError("audit failed")
                count = await revoke_idp_sessions(
                    test_db_session,
                    idp_id,
                    idp_name="FailIdP",
                    actor_username="admin",
                    actor_source="api",
                )

        assert count == 2
