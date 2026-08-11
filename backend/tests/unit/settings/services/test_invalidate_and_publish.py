"""Unit tests for _invalidate_and_publish helper in settings service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from syntara.settings.services.settings_service import _invalidate_and_publish


class TestInvalidateAndPublish:
    """Tests for _invalidate_and_publish()."""

    @pytest.mark.asyncio
    async def test_calls_invalidate_and_publish(self) -> None:
        """Calls both invalidate and publish_change on the cache."""
        mock_cache = AsyncMock()
        mock_cache.invalidate = AsyncMock()
        mock_cache.publish_change = AsyncMock()

        with patch(
            "syntara.settings.services.settings_service.get_runtime_settings",
            return_value=mock_cache,
        ):
            await _invalidate_and_publish("test.key")

        mock_cache.invalidate.assert_awaited_once_with("test.key")
        mock_cache.publish_change.assert_awaited_once_with("test.key")

    @pytest.mark.asyncio
    async def test_suppresses_runtime_error(self) -> None:
        """Does not raise when cache is not initialized."""
        with patch(
            "syntara.settings.services.settings_service.get_runtime_settings",
            side_effect=RuntimeError("not initialized"),
        ):
            # Should not raise
            await _invalidate_and_publish("test.key")
