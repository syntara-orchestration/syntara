"""Unit tests for rate limiting settings helpers."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from syntara.rate_limiting.settings import (
    RATE_LIMIT_REQUESTS_PER_WINDOW,
    RATE_LIMIT_WINDOW_DURATION_SECONDS,
    get_rate_limit_config,
)


@pytest.fixture
def mock_settings_cache() -> AsyncMock:
    """Mock settings cache for rate limit config lookups."""
    return AsyncMock()


class TestGetRateLimitConfig:
    """Tests for get_rate_limit_config."""

    @pytest.mark.asyncio
    async def test_disabled_when_zero(self, mock_settings_cache: AsyncMock) -> None:
        mock_settings_cache.get_int.return_value = 0

        result = await get_rate_limit_config(mock_settings_cache)

        assert result is None

    @pytest.mark.asyncio
    async def test_disabled_when_none(self, mock_settings_cache: AsyncMock) -> None:
        mock_settings_cache.get_int.return_value = None

        result = await get_rate_limit_config(mock_settings_cache)

        assert result is None

    @pytest.mark.asyncio
    async def test_enabled_with_custom_window(self, mock_settings_cache: AsyncMock) -> None:
        async def side_effect(key: str) -> int | None:
            if key == RATE_LIMIT_REQUESTS_PER_WINDOW:
                return 100
            if key == RATE_LIMIT_WINDOW_DURATION_SECONDS:
                return 120
            return None

        mock_settings_cache.get_int.side_effect = side_effect

        result = await get_rate_limit_config(mock_settings_cache)

        assert result == (100, 120)

    @pytest.mark.asyncio
    async def test_enabled_with_catalog_default_window(self, mock_settings_cache: AsyncMock) -> None:
        async def side_effect(key: str) -> int | None:
            if key == RATE_LIMIT_REQUESTS_PER_WINDOW:
                return 50
            if key == RATE_LIMIT_WINDOW_DURATION_SECONDS:
                return 60  # catalog default
            return None

        mock_settings_cache.get_int.side_effect = side_effect

        result = await get_rate_limit_config(mock_settings_cache)

        assert result is not None
        assert result[0] == 50
        assert result[1] == 60
