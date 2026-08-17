"""Integration tests for authorization input validation.

Covers CHAOS-002, CHAOS-005, CHAOS-006, and CHAOS-045: malformed requests
and edge cases in request handling.
"""

import pytest
from httpx import AsyncClient

from syntara.core.models import User

# ============================================================================
# CHAOS-002: Missing Required Fields → 422
# ============================================================================


class TestMissingRequiredFields:
    """Verify API returns 422 for missing required fields."""

    @pytest.mark.asyncio
    async def test_can_i_missing_action(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        """CHAOS-002a: can-i without action field returns 422."""
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"resource_type": "workflow"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_can_i_missing_resource_type(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        """CHAOS-002b: can-i without resource_type field returns 422."""
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": "read"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_can_i_empty_body(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        """CHAOS-002c: can-i with empty body returns 422."""
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_who_can_missing_fields(
        self,
        auth_client_as_admin: AsyncClient,
    ) -> None:
        """CHAOS-002d: who-can without required fields returns 422."""
        resp = await auth_client_as_admin.post(
            "/api/v1/authz/who_can",
            json={},
        )
        assert resp.status_code == 422

        resp = await auth_client_as_admin.post(
            "/api/v1/authz/who_can",
            json={"action": "read"},
        )
        assert resp.status_code == 422


# ============================================================================
# CHAOS-005: Very Long Action Strings
# ============================================================================


class TestLongActionStrings:
    """Verify API handles very long action strings gracefully."""

    @pytest.mark.asyncio
    async def test_can_i_long_action(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        """CHAOS-005a: Long action string is handled (denied, not crashed)."""
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": "a" * 10000, "resource_type": "workflow"},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False

    @pytest.mark.asyncio
    async def test_can_i_long_resource_type(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        """CHAOS-005b: Long resource_type is handled (denied, not crashed)."""
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": "read", "resource_type": "x" * 10000},
        )
        assert resp.status_code == 200
        assert resp.json()["allowed"] is False


# ============================================================================
# CHAOS-006: Wrong Types → 422
# ============================================================================


class TestWrongTypes:
    """Verify API returns 422 for wrong field types."""

    @pytest.mark.asyncio
    async def test_can_i_action_is_dict(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        """CHAOS-006a: Dict where string expected returns 422."""
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": {"nested": "value"}, "resource_type": "workflow"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_can_i_action_is_list(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        """CHAOS-006b: List where string expected returns 422."""
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": ["read", "write"], "resource_type": "workflow"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_can_i_action_is_number(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        """CHAOS-006c: Number where string expected returns 422."""
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={"action": 42, "resource_type": "workflow"},
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_can_i_resource_labels_not_dict(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        """CHAOS-008: resource_labels as string returns 422."""
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={
                "action": "read",
                "resource_type": "workflow",
                "resource_labels": "not-a-dict",
            },
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_can_i_resource_labels_nested_values(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        """CHAOS-008b: Nested values in resource_labels returns 422."""
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={
                "action": "read",
                "resource_type": "workflow",
                "resource_labels": {"env": {"nested": "value"}},
            },
        )
        assert resp.status_code == 422


# ============================================================================
# CHAOS-045: Extra Unknown Fields Ignored Safely
# ============================================================================


class TestExtraFieldsIgnored:
    """Verify unknown fields in request body are ignored safely."""

    @pytest.mark.asyncio
    async def test_can_i_extra_fields_ignored(
        self,
        auth_client: AsyncClient,
        test_user: User,
    ) -> None:
        """CHAOS-045a: Extra unknown fields in can-i body are ignored."""
        resp = await auth_client.post(
            "/api/v1/authz/can_i",
            json={
                "action": "read",
                "resource_type": "workflow",
                "unknown_field": "should_be_ignored",
                "another_extra": 42,
                "nested_extra": {"deeply": "nested"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "allowed" in data

    @pytest.mark.asyncio
    async def test_who_can_extra_fields_ignored(
        self,
        auth_client_as_admin: AsyncClient,
    ) -> None:
        """CHAOS-045b: Extra unknown fields in who-can body are ignored."""
        resp = await auth_client_as_admin.post(
            "/api/v1/authz/who_can",
            json={
                "action": "read",
                "resource_type": "workflow",
                "sneaky_field": "should_be_ignored",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "resources" in data
