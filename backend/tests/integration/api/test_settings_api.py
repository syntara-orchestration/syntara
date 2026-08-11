"""Integration tests for the settings REST API endpoints.

Tests the full HTTP cycle: auth → router → service → DB → response serialization.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from syntara.auth import get_current_user
from syntara.core.database.session import get_db

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable

    from fastapi import FastAPI
    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.models import User


@pytest_asyncio.fixture
async def admin_settings_client(
    test_db_session: AsyncSession,
    session_app: FastAPI,
    user_factory: Callable[..., Awaitable[User]],
) -> AsyncGenerator[AsyncClient, None]:
    """Authenticated admin client for settings integration tests."""
    admin = await user_factory()

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield test_db_session

    async def override_get_current_user() -> User:
        return admin

    from tests.integration.fixtures.client import _scoped_overrides

    async with _scoped_overrides(session_app):
        session_app.dependency_overrides[get_db] = override_get_db
        session_app.dependency_overrides[get_current_user] = override_get_current_user

        # Mock evaluator to always allow — integration tests validate API behavior, not authz.
        mock_evaluator = AsyncMock()
        mock_evaluator.evaluate = MagicMock(
            return_value={
                "allow": True,
                "deny": False,
                "matched_policy": "test-allow-all",
                "allowed_projects": ["*"],
            }
        )

        def _mock_getter(request: Any = None) -> AsyncMock:  # noqa: ANN401
            return mock_evaluator

        with (
            patch("syntara.authz.dependencies.get_authz_evaluator", _mock_getter),
            patch("syntara.authz.dependencies.get_authz_evaluator", _mock_getter),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=session_app),
                base_url="http://test",
            ) as client:
                yield client


class TestListSettings:
    """Tests for GET /api/v1/settings."""

    @pytest.mark.asyncio
    async def test_list_settings_returns_200(self, admin_settings_client: AsyncClient) -> None:
        """GET /settings returns 200 with resources array."""
        response = await admin_settings_client.get("/api/v1/settings")

        assert response.status_code == 200
        data = response.json()
        assert "resources" in data
        assert isinstance(data["resources"], list)
        assert "next" in data
        assert "prev" in data

    @pytest.mark.asyncio
    async def test_list_settings_filter_by_category(self, admin_settings_client: AsyncClient) -> None:
        """GET /settings?category=context_manager filters correctly."""
        response = await admin_settings_client.get("/api/v1/settings", params={"category": "context_manager"})

        assert response.status_code == 200
        data = response.json()
        for setting in data["resources"]:
            assert setting["category"] == "context_manager"


class TestGetSetting:
    """Tests for GET /api/v1/settings/{key}."""

    @pytest.mark.asyncio
    async def test_get_setting_returns_200(self, admin_settings_client: AsyncClient) -> None:
        """GET /settings/{key} returns a setting with all expected fields."""
        response = await admin_settings_client.get("/api/v1/settings/context_manager.max_total_tokens")

        assert response.status_code == 200
        data = response.json()
        assert data["key"] == "context_manager.max_total_tokens"
        assert "value" in data
        assert "default_value" in data
        assert "effective_value" in data
        assert "version" in data
        assert "value_type" in data
        assert "helper_text" in data
        assert "depends_on" in data

    @pytest.mark.asyncio
    async def test_get_setting_not_found(self, admin_settings_client: AsyncClient) -> None:
        """GET /settings/{key} returns 404 for unknown key."""
        response = await admin_settings_client.get("/api/v1/settings/nonexistent.setting.key")

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_setting_invalid_key_format(self, admin_settings_client: AsyncClient) -> None:
        """GET /settings/{key} returns 400 for malformed key."""
        response = await admin_settings_client.get("/api/v1/settings/INVALID")

        assert response.status_code == 400


class TestUpdateSetting:
    """Tests for PATCH /api/v1/settings/{key}."""

    @pytest.mark.asyncio
    async def test_update_setting_with_version(self, admin_settings_client: AsyncClient) -> None:
        """PATCH /settings/{key} with expected_version returns 200."""
        # Get current version
        get_response = await admin_settings_client.get("/api/v1/settings/context_manager.max_total_tokens")
        current = get_response.json()
        original_value = current["effective_value"]
        version = current["version"]

        try:
            # Update
            response = await admin_settings_client.patch(
                "/api/v1/settings/context_manager.max_total_tokens",
                json={"value": 9999, "expected_version": version},
            )

            assert response.status_code == 200
            data = response.json()
            assert data["effective_value"] == 9999
            assert data["version"] == version + 1
        finally:
            # Reset to original
            get_response = await admin_settings_client.get("/api/v1/settings/context_manager.max_total_tokens")
            new_version = get_response.json()["version"]
            await admin_settings_client.patch(
                "/api/v1/settings/context_manager.max_total_tokens",
                json={"value": original_value, "expected_version": new_version},
            )

    @pytest.mark.asyncio
    async def test_update_setting_without_version(self, admin_settings_client: AsyncClient) -> None:
        """PATCH /settings/{key} without expected_version returns 200."""
        get_response = await admin_settings_client.get("/api/v1/settings/context_manager.max_total_tokens")
        original_value = get_response.json()["effective_value"]

        try:
            response = await admin_settings_client.patch(
                "/api/v1/settings/context_manager.max_total_tokens",
                json={"value": 7777},
            )

            assert response.status_code == 200
            assert response.json()["effective_value"] == 7777
        finally:
            await admin_settings_client.patch(
                "/api/v1/settings/context_manager.max_total_tokens",
                json={"value": original_value},
            )

    @pytest.mark.asyncio
    async def test_update_setting_version_conflict(self, admin_settings_client: AsyncClient) -> None:
        """PATCH /settings/{key} with wrong version returns 409."""
        response = await admin_settings_client.patch(
            "/api/v1/settings/context_manager.max_total_tokens",
            json={"value": 5000, "expected_version": 99999},
        )

        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_update_setting_null_value_rejected(self, admin_settings_client: AsyncClient) -> None:
        """PATCH /settings/{key} with null value returns 422."""
        response = await admin_settings_client.patch(
            "/api/v1/settings/context_manager.max_total_tokens",
            json={"value": None, "expected_version": 1},
        )

        assert response.status_code == 422


class TestBulkUpdate:
    """Tests for PATCH /api/v1/settings."""

    @pytest.mark.asyncio
    async def test_bulk_update_returns_200(self, admin_settings_client: AsyncClient) -> None:
        """PATCH /settings with updates array returns 200."""
        # Get current values
        r1 = await admin_settings_client.get("/api/v1/settings/context_manager.max_total_tokens")
        r2 = await admin_settings_client.get("/api/v1/settings/context_manager.max_context_tokens")
        orig1 = r1.json()
        orig2 = r2.json()

        try:
            response = await admin_settings_client.patch(
                "/api/v1/settings",
                json={
                    "updates": [
                        {"key": "context_manager.max_total_tokens", "value": 8888},
                        {"key": "context_manager.max_context_tokens", "value": 4444},
                    ]
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert len(data["resources"]) == 2
        finally:
            await admin_settings_client.patch(
                "/api/v1/settings",
                json={
                    "updates": [
                        {"key": "context_manager.max_total_tokens", "value": orig1["effective_value"]},
                        {"key": "context_manager.max_context_tokens", "value": orig2["effective_value"]},
                    ]
                },
            )

    @pytest.mark.asyncio
    async def test_bulk_update_duplicate_keys_rejected(self, admin_settings_client: AsyncClient) -> None:
        """PATCH /settings with duplicate keys returns 400."""
        response = await admin_settings_client.patch(
            "/api/v1/settings",
            json={
                "updates": [
                    {"key": "context_manager.max_total_tokens", "value": 1000},
                    {"key": "context_manager.max_total_tokens", "value": 2000},
                ]
            },
        )

        assert response.status_code == 400


class TestListCategories:
    """Tests for GET /api/v1/settings/categories."""

    @pytest.mark.asyncio
    async def test_list_categories_returns_200(self, admin_settings_client: AsyncClient) -> None:
        """GET /settings/categories returns categories with expected fields."""
        response = await admin_settings_client.get("/api/v1/settings/categories")

        assert response.status_code == 200
        data = response.json()
        assert "resources" in data
        assert isinstance(data["resources"], list)
        assert len(data["resources"]) > 0

        cat = data["resources"][0]
        assert "slug" in cat
        assert "name" in cat
        assert "display_order" in cat
        assert "group_names" in cat


class TestAuth:
    """Tests for auth enforcement on settings endpoints."""

    @pytest.mark.asyncio
    async def test_unauthenticated_gets_401(self, base_client: AsyncClient) -> None:
        """GET /settings without authentication returns 401."""
        response = await base_client.get("/api/v1/settings")

        assert response.status_code == 401
