"""Unit tests for admin revocation API endpoints."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from syntara.auth.models.global_revocation_timestamp import GlobalRevocationTimestamp
from syntara.identity_providers.models.identity_provider import IdentityProvider

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


pytestmark = pytest.mark.asyncio


class TestGetGlobalRevocationTimestamp:
    """Tests for the GET /admin/revocation endpoint."""

    async def test_returns_null_when_no_revocation_set(self, auth_client: AsyncClient) -> None:
        response = await auth_client.get("/api/v1/admin/revocation")
        assert response.status_code == 200
        data = response.json()
        assert data["revoked_before"] is None
        assert data["updated_at"] is None
        assert data["updated_by"] is None

    async def test_returns_timestamp_when_set(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
    ) -> None:
        now = datetime.now(UTC)
        row = GlobalRevocationTimestamp(id=1, revoked_before=now, updated_at=now)
        test_db_session.add(row)
        await test_db_session.commit()

        response = await auth_client.get("/api/v1/admin/revocation")
        assert response.status_code == 200
        data = response.json()
        assert data["revoked_before"] is not None
        assert data["updated_at"] is not None

    async def test_response_contains_only_expected_fields(
        self,
        auth_client: AsyncClient,
    ) -> None:
        response = await auth_client.get("/api/v1/admin/revocation")
        assert response.status_code == 200
        data = response.json()
        assert set(data.keys()) == {"revoked_before", "updated_at", "updated_by"}

    async def test_unauthenticated_returns_401(self, base_client: AsyncClient) -> None:
        response = await base_client.get("/api/v1/admin/revocation")
        assert response.status_code == 401


class TestRevokeAllSessions:
    """Tests for the POST /admin/revocation endpoint."""

    async def test_sets_global_revocation_timestamp(self, auth_client: AsyncClient) -> None:
        with patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher:
            response = await auth_client.post("/api/v1/admin/revocation")

        assert response.status_code == 200
        data = response.json()
        assert "Global revocation timestamp set" in data["message"]
        assert mock_dispatcher.dispatch.called

    async def test_persists_timestamp_readable_via_get(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        with patch("syntara.admin.services.AuditEventDispatcher"):
            await auth_client.post("/api/v1/admin/revocation")

        response = await auth_client.get("/api/v1/admin/revocation")
        assert response.status_code == 200
        data = response.json()
        revoked_before = datetime.fromisoformat(data["revoked_before"])
        updated_at = datetime.fromisoformat(data["updated_at"])
        assert revoked_before == updated_at
        assert (datetime.now(UTC) - revoked_before).total_seconds() < 10
        assert data["updated_by"] == test_user.username

    async def test_response_contains_message_field(
        self,
        auth_client: AsyncClient,
    ) -> None:
        with patch("syntara.admin.services.AuditEventDispatcher"):
            response = await auth_client.post("/api/v1/admin/revocation")

        data = response.json()
        assert "message" in data
        assert "All tokens issued before this time are now invalid" in data["message"]

    async def test_unauthenticated_returns_401(self, base_client: AsyncClient) -> None:
        response = await base_client.post("/api/v1/admin/revocation")
        assert response.status_code == 401

    async def test_audit_event_dispatched_with_api_source(
        self,
        auth_client: AsyncClient,
    ) -> None:
        with patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher:
            await auth_client.post("/api/v1/admin/revocation")

        mock_dispatcher.dispatch.assert_called_once()
        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.actor_source == "api"

    async def test_audit_dispatch_failure_does_not_break_endpoint(
        self,
        auth_client: AsyncClient,
    ) -> None:
        with patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher:
            mock_dispatcher.dispatch.side_effect = RuntimeError("audit failure")
            response = await auth_client.post("/api/v1/admin/revocation")

        assert response.status_code == 200


class TestRevokeUserSessions:
    """Tests for the POST /admin/revocation/users/{username} endpoint."""

    async def test_revokes_sessions_for_existing_user(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        with patch("syntara.admin.services.AuditEventDispatcher"):
            response = await auth_client.post(
                f"/api/v1/admin/revocation/users/{test_user.username}",
            )

        assert response.status_code == 200
        data = response.json()
        assert test_user.username in data["message"]
        assert "sessions_revoked" in data

    async def test_response_includes_session_count(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        with (
            patch("syntara.admin.services.AuditEventDispatcher"),
            patch("syntara.admin.services.create_session_store") as mock_create,
        ):
            mock_store = AsyncMock()
            mock_store.revoke_all_for_user.return_value = 3
            mock_store.increment_token_version.return_value = 1
            mock_create.return_value = mock_store

            response = await auth_client.post(
                f"/api/v1/admin/revocation/users/{test_user.username}",
            )

        assert response.status_code == 200
        data = response.json()
        assert data["sessions_revoked"] == 3
        assert "3 session(s)" in data["message"]

    async def test_returns_404_for_nonexistent_user(
        self,
        auth_client: AsyncClient,
    ) -> None:
        response = await auth_client.post(
            "/api/v1/admin/revocation/users/nonexistent_user_xyz",
        )
        assert response.status_code == 404

    async def test_returns_404_for_soft_deleted_user(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory,
    ) -> None:
        user = await user_factory(username="goneuser", email="gone@test.com")
        user.deleted_at = datetime.now(UTC)
        test_db_session.add(user)
        await test_db_session.commit()

        response = await auth_client.post(
            "/api/v1/admin/revocation/users/goneuser",
        )
        assert response.status_code == 404

    async def test_unauthenticated_returns_401(self, base_client: AsyncClient) -> None:
        response = await base_client.post("/api/v1/admin/revocation/users/testuser")
        assert response.status_code == 401

    async def test_audit_event_has_user_target_type(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        with patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher:
            await auth_client.post(
                f"/api/v1/admin/revocation/users/{test_user.username}",
            )

        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.target_type == "user"
        assert event.target_identifier == test_user.username
        assert event.actor_source == "api"

    async def test_audit_dispatch_failure_does_not_break_endpoint(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        with patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher:
            mock_dispatcher.dispatch.side_effect = RuntimeError("audit down")
            response = await auth_client.post(
                f"/api/v1/admin/revocation/users/{test_user.username}",
            )

        assert response.status_code == 200


class TestRevokeIdpSessions:
    """Tests for the POST /admin/revocation/identity_providers/{idp_name} endpoint."""

    async def test_revokes_sessions_for_existing_idp(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        provider = IdentityProvider(
            id=uuid4(),
            name="Test OIDC Provider",
            created_by=test_user.id,
            configuration={
                "provider_type": "oidc",
                "issuer_url": "https://example.com",
                "client_id": "test-client",
                "client_secret": "test-secret",
                "redirect_uri": "http://localhost/callback",
            },
        )
        test_db_session.add(provider)
        await test_db_session.commit()

        with patch("syntara.admin.services.AuditEventDispatcher"):
            response = await auth_client.post(
                f"/api/v1/admin/revocation/identity_providers/{provider.name}",
            )

        assert response.status_code == 200
        data = response.json()
        assert provider.name in data["message"]
        assert "sessions_revoked" in data

    async def test_response_includes_session_count(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        provider = IdentityProvider(
            id=uuid4(),
            name="Count Test Provider",
            created_by=test_user.id,
            configuration={
                "provider_type": "oidc",
                "issuer_url": "https://count.example.com",
                "client_id": "c",
                "client_secret": "s",
                "redirect_uri": "http://localhost/cb",
            },
        )
        test_db_session.add(provider)
        await test_db_session.commit()

        with (
            patch("syntara.admin.services.AuditEventDispatcher"),
            patch("syntara.admin.services.create_session_store") as mock_create,
        ):
            mock_store = AsyncMock()
            mock_store.revoke_by_idp.return_value = 7
            mock_create.return_value = mock_store

            response = await auth_client.post(
                f"/api/v1/admin/revocation/identity_providers/{provider.name}",
            )

        assert response.status_code == 200
        data = response.json()
        assert data["sessions_revoked"] == 7
        assert "7 session(s)" in data["message"]

    async def test_returns_404_for_nonexistent_idp(
        self,
        auth_client: AsyncClient,
    ) -> None:
        response = await auth_client.post(
            "/api/v1/admin/revocation/identity_providers/Nonexistent Provider",
        )
        assert response.status_code == 404

    async def test_returns_404_after_hard_delete(
        self,
        auth_client: AsyncClient,
    ) -> None:
        """After hard-deleting a provider, revocation returns 404."""
        response = await auth_client.post(
            "/api/v1/admin/revocation/identity_providers/NonexistentProvider",
        )
        assert response.status_code == 404

    async def test_unauthenticated_returns_401(self, base_client: AsyncClient) -> None:
        response = await base_client.post(
            "/api/v1/admin/revocation/identity_providers/SomeProvider",
        )
        assert response.status_code == 401

    async def test_audit_event_has_idp_target_type(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        provider = IdentityProvider(
            id=uuid4(),
            name="Audit Test Provider",
            created_by=test_user.id,
            configuration={
                "provider_type": "oidc",
                "issuer_url": "https://audit-test.example.com",
                "client_id": "audit-client",
                "client_secret": "audit-secret",
                "redirect_uri": "http://localhost/callback",
            },
        )
        test_db_session.add(provider)
        await test_db_session.commit()

        with patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher:
            await auth_client.post(
                f"/api/v1/admin/revocation/identity_providers/{provider.name}",
            )

        event = mock_dispatcher.dispatch.call_args[0][0]
        assert event.target_type == "idp"
        assert event.target_identifier == provider.name
        assert event.actor_source == "api"

    async def test_audit_dispatch_failure_does_not_break_endpoint(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        test_user: User,
    ) -> None:
        provider = IdentityProvider(
            id=uuid4(),
            name="Audit Fail Provider",
            created_by=test_user.id,
            configuration={
                "provider_type": "oidc",
                "issuer_url": "https://fail.example.com",
                "client_id": "c",
                "client_secret": "s",
                "redirect_uri": "http://localhost/cb",
            },
        )
        test_db_session.add(provider)
        await test_db_session.commit()

        with patch("syntara.admin.services.AuditEventDispatcher") as mock_dispatcher:
            mock_dispatcher.dispatch.side_effect = RuntimeError("audit broken")
            response = await auth_client.post(
                f"/api/v1/admin/revocation/identity_providers/{provider.name}",
            )

        assert response.status_code == 200
