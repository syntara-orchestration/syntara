"""Integration tests for invocation endpoint authorization (AAP-74615).

Verifies that invocation endpoints enforce admin-only access
instead of the previous NO_PERMISSION (open to all authenticated users).
"""

from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from tests.integration.api.conftest import make_admin, make_user_role


class TestInvocationAuthz:
    """Verify invocation endpoints require admin role."""

    @pytest.mark.asyncio
    async def test_non_admin_cannot_create_invocation(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Regular user cannot POST /invocations."""
        user = await user_factory(username="inv-user1", email="inv-user1@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.post(
            "/api/v1/invocations",
            json={"prompt": "test prompt", "session_id": "test-session"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_list_invocations(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Regular user cannot GET /invocations."""
        user = await user_factory(username="inv-user2", email="inv-user2@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get("/api/v1/invocations")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_create_invocation_chat(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Regular user cannot POST /invocations/chat."""
        user = await user_factory(username="inv-user1b", email="inv-user1b@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.post(
            "/api/v1/invocations/chat",
            data={"prompt": "test prompt", "session_id": "test-session"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_get_invocation(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Regular user cannot GET /invocations/{id}."""
        user = await user_factory(username="inv-user3", email="inv-user3@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.get(f"/api/v1/invocations/{uuid4()}")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_cannot_cancel_invocation(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Regular user cannot POST /invocations/{id}/cancel."""
        user = await user_factory(username="inv-user4", email="inv-user4@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        resp = await auth_client.post(
            f"/api/v1/invocations/{uuid4()}/cancel",
            json={"reason": "test"},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_admin_denied_via_can_i(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """can-i confirms invocation actions are denied for regular user."""
        user = await user_factory(username="inv-user5", email="inv-user5@test.com")
        await make_user_role(test_db_session, user)
        auth_as(user)

        for action in ("create", "read", "cancel"):
            resp = await auth_client.post(
                "/api/v1/authz/can_i",
                json={"action": action, "resource_type": "invocation"},
            )
            assert resp.status_code == 200
            assert resp.json()["allowed"] is False, f"User should not have invocation:{action}"

    @pytest.mark.asyncio
    async def test_admin_can_list_invocations(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """Admin user can GET /invocations."""
        admin = await user_factory(username="inv-admin1", email="inv-admin1@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        resp = await auth_client.get("/api/v1/invocations")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_admin_allowed_via_can_i(
        self,
        auth_client: AsyncClient,
        test_db_session: AsyncSession,
        user_factory: Callable[..., Awaitable[User]],
        auth_as: Callable[[User], None],
    ) -> None:
        """can-i confirms invocation actions are allowed for admin."""
        admin = await user_factory(username="inv-admin2", email="inv-admin2@test.com")
        await make_admin(test_db_session, admin)
        auth_as(admin)

        for action in ("create", "read", "cancel"):
            resp = await auth_client.post(
                "/api/v1/authz/can_i",
                json={"action": action, "resource_type": "invocation"},
            )
            assert resp.status_code == 200
            assert resp.json()["allowed"] is True, f"Admin should have invocation:{action}"
