"""Integration tests for auditor read-only access to settings endpoints.

Verifies that users with the auditor role can read settings but cannot
modify them, using the real Rego rego policy evaluation.
"""

from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from tests.integration.api.conftest import make_auditor


class TestAuditorSettingsAccess:
    """Auditor role grants read-only access to settings."""

    @pytest.mark.asyncio
    async def test_auditor_can_list_settings(
        self,
        auth_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
        test_db_session: AsyncSession,
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor can GET /settings and receive a 200 response."""
        auditor = await user_factory(username="auditor-list", email="auditor-list@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.get("/api/v1/settings")
        assert resp.status_code == 200
        assert "resources" in resp.json()

    @pytest.mark.asyncio
    async def test_auditor_can_list_categories(
        self,
        auth_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
        test_db_session: AsyncSession,
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor can GET /settings/categories and receive a 200 response."""
        auditor = await user_factory(username="auditor-cats", email="auditor-cats@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.get("/api/v1/settings/categories")
        assert resp.status_code == 200
        assert "resources" in resp.json()

    @pytest.mark.asyncio
    async def test_auditor_can_get_setting(
        self,
        auth_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
        test_db_session: AsyncSession,
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor can GET /settings/{key} and receive a 200 response."""
        auditor = await user_factory(username="auditor-get", email="auditor-get@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.get("/api/v1/settings/context_manager.max_total_tokens")
        assert resp.status_code == 200
        assert resp.json()["key"] == "context_manager.max_total_tokens"

    @pytest.mark.asyncio
    async def test_auditor_cannot_update_setting(
        self,
        auth_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
        test_db_session: AsyncSession,
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor is denied PATCH /settings/{key} with 403."""
        auditor = await user_factory(username="auditor-patch", email="auditor-patch@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.patch(
            "/api/v1/settings/context_manager.max_total_tokens",
            json={"value": 9999},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_auditor_cannot_bulk_update_settings(
        self,
        auth_client: AsyncClient,
        user_factory: Callable[..., Awaitable[User]],
        test_db_session: AsyncSession,
        auth_as: Callable[[User], None],
    ) -> None:
        """Auditor is denied PATCH /settings (bulk update) with 403."""
        auditor = await user_factory(username="auditor-bulk", email="auditor-bulk@test.com")
        await make_auditor(test_db_session, auditor)
        auth_as(auditor)

        resp = await auth_client.patch(
            "/api/v1/settings",
            json={
                "updates": [
                    {"key": "context_manager.max_total_tokens", "value": 9999},
                ]
            },
        )
        assert resp.status_code == 403
