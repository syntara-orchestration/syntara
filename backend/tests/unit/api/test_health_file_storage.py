"""Tests for file storage health check and S3 startup validation.

Health endpoint tests call the health_check function directly (not via HTTP client)
to isolate the file storage logic from the full ASGI stack.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from syntara.files.health import check_file_storage_health, validate_file_storage_at_startup

# ---------------------------------------------------------------------------
# check_file_storage_health
# ---------------------------------------------------------------------------


class TestCheckFileStorageHealth:
    """Verify check_file_storage_health returns the correct status string."""

    @pytest.mark.asyncio
    async def test_returns_ok_when_healthy(self) -> None:
        mock_retriever = AsyncMock()
        mock_retriever.health_check = AsyncMock(return_value=True)

        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=True)
        mock_fm.get_retriever.return_value = mock_retriever

        with patch("syntara.files.health.get_file_manager", return_value=mock_fm):
            result = await check_file_storage_health()

        assert result == "ok"

    @pytest.mark.asyncio
    async def test_returns_degraded_when_unhealthy(self) -> None:
        mock_retriever = AsyncMock()
        mock_retriever.health_check = AsyncMock(return_value=False)

        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=True)
        mock_fm.get_retriever.return_value = mock_retriever

        with patch("syntara.files.health.get_file_manager", return_value=mock_fm):
            result = await check_file_storage_health()

        assert result == "degraded"

    @pytest.mark.asyncio
    async def test_returns_unconfigured_when_s3_not_set(self) -> None:
        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=False)

        with patch("syntara.files.health.get_file_manager", return_value=mock_fm):
            result = await check_file_storage_health()

        assert result == "unconfigured"

    @pytest.mark.asyncio
    async def test_returns_error_on_exception(self) -> None:
        with patch("syntara.files.health.get_file_manager", side_effect=RuntimeError("boom")):
            result = await check_file_storage_health()

        assert result == "error"

    @pytest.mark.asyncio
    async def test_returns_degraded_on_timeout(self) -> None:
        mock_retriever = AsyncMock()
        mock_retriever.health_check = AsyncMock(side_effect=TimeoutError)

        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=True)
        mock_fm.get_retriever.return_value = mock_retriever

        with (
            patch("syntara.files.health.get_file_manager", return_value=mock_fm),
            patch("syntara.files.health.HEALTH_CHECK_TIMEOUT_SECONDS", 0.001),
        ):
            result = await check_file_storage_health()

        assert result == "degraded"


# ---------------------------------------------------------------------------
# validate_file_storage_at_startup
# ---------------------------------------------------------------------------


class TestStartupValidation:
    """Verify validate_file_storage_at_startup logs warnings (never raises)."""

    @pytest.mark.asyncio
    async def test_warns_when_s3_unconfigured(self) -> None:
        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=False)

        with (
            patch("syntara.files.health.get_file_manager", return_value=mock_fm),
            patch("syntara.files.health.logger") as mock_logger,
        ):
            from syntara.core.config.base import get_settings

            await validate_file_storage_at_startup(get_settings())

        mock_logger.warning.assert_called_once()
        mock_fm.get_retriever.assert_not_called()

    @pytest.mark.asyncio
    async def test_succeeds_when_s3_healthy(self) -> None:
        mock_retriever = AsyncMock()
        mock_retriever.health_check = AsyncMock(return_value=True)

        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=True)
        mock_fm.get_retriever.return_value = mock_retriever

        with (
            patch("syntara.files.health.get_file_manager", return_value=mock_fm),
            patch("syntara.files.health.logger") as mock_logger,
        ):
            from syntara.core.config.base import get_settings

            await validate_file_storage_at_startup(get_settings())

        mock_logger.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_warns_when_s3_unreachable(self) -> None:
        """S3 configured but unreachable — warns, does NOT raise."""
        mock_retriever = AsyncMock()
        mock_retriever.health_check = AsyncMock(return_value=False)

        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=True)
        mock_fm.get_retriever.return_value = mock_retriever

        with (
            patch("syntara.files.health.get_file_manager", return_value=mock_fm),
            patch("syntara.files.health.logger") as mock_logger,
        ):
            from syntara.core.config.base import get_settings

            await validate_file_storage_at_startup(get_settings())

        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_warns_on_health_check_timeout(self) -> None:
        """S3 configured but health check times out — warns, does NOT raise."""
        mock_retriever = AsyncMock()
        mock_retriever.health_check = AsyncMock(side_effect=TimeoutError)

        mock_fm = MagicMock()
        type(mock_fm).s3_configured = PropertyMock(return_value=True)
        mock_fm.get_retriever.return_value = mock_retriever

        with (
            patch("syntara.files.health.get_file_manager", return_value=mock_fm),
            patch("syntara.files.health.HEALTH_CHECK_TIMEOUT_SECONDS", 0.001),
            patch("syntara.files.health.logger") as mock_logger,
        ):
            from syntara.core.config.base import get_settings

            await validate_file_storage_at_startup(get_settings())

        mock_logger.warning.assert_called_once()
