"""Tests for runtime log level configuration."""

import logging
from unittest.mock import AsyncMock, patch

from syntara.core.logging.logging import (
    _set_log_level,
    apply_runtime_log_level,
    build_uvicorn_logging_config,
)
from syntara.settings.cache.settings_cache import SettingsCache


class TestSetLogLevel:
    """Tests for _set_log_level."""

    def test_sets_root_logger_level(self) -> None:
        root = logging.getLogger()
        original = root.level
        try:
            _set_log_level("DEBUG")
            assert root.level == logging.DEBUG
        finally:
            root.setLevel(original)

    def test_sets_uvicorn_logger_levels(self) -> None:
        names = ("uvicorn", "uvicorn.error", "uvicorn.access")
        originals = {n: logging.getLogger(n).level for n in names}
        try:
            _set_log_level("WARNING")
            for name in names:
                assert logging.getLogger(name).level == logging.WARNING
        finally:
            for name, level in originals.items():
                logging.getLogger(name).setLevel(level)


class TestBuildUvicornLoggingConfig:
    """Tests for build_uvicorn_logging_config."""

    def test_returns_valid_logging_config(self) -> None:
        config = build_uvicorn_logging_config("INFO")
        assert config["version"] == 1
        assert config["disable_existing_loggers"] is False
        assert "syntara" in config["formatters"]
        assert "syntara" in config["handlers"]

    def test_uses_provided_log_level(self) -> None:
        config = build_uvicorn_logging_config("DEBUG")
        assert config["loggers"]["uvicorn"]["level"] == "DEBUG"
        assert config["loggers"]["uvicorn.error"]["level"] == "DEBUG"
        assert config["loggers"]["uvicorn.access"]["level"] == "DEBUG"
        assert config["root"]["level"] == "DEBUG"

    def test_different_levels(self) -> None:
        for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
            config = build_uvicorn_logging_config(level)
            assert config["root"]["level"] == level


class TestApplyRuntimeLogLevel:
    """Tests for apply_runtime_log_level."""

    async def test_applies_level_from_runtime_settings(self) -> None:
        mock_cache = AsyncMock(spec=SettingsCache)
        mock_cache.get_str.return_value = "DEBUG"

        with patch(
            "syntara.settings.cache.settings_cache.get_runtime_settings",
            return_value=mock_cache,
        ):
            root = logging.getLogger()
            original = root.level
            try:
                await apply_runtime_log_level()
                assert root.level == logging.DEBUG
            finally:
                root.setLevel(original)

    async def test_falls_back_to_static_config_on_error(self) -> None:
        with (
            patch(
                "syntara.settings.cache.settings_cache.get_runtime_settings",
                side_effect=RuntimeError("no cache"),
            ),
            patch(
                "syntara.core.logging.logging.settings",
            ) as mock_settings,
        ):
            mock_settings.fallback_log_level = "ERROR"
            root = logging.getLogger()
            original = root.level
            try:
                await apply_runtime_log_level()
                assert root.level == logging.ERROR
            finally:
                root.setLevel(original)

    async def test_normalizes_level_to_uppercase(self) -> None:
        mock_cache = AsyncMock(spec=SettingsCache)
        mock_cache.get_str.return_value = "warning"

        with patch(
            "syntara.settings.cache.settings_cache.get_runtime_settings",
            return_value=mock_cache,
        ):
            root = logging.getLogger()
            original = root.level
            try:
                await apply_runtime_log_level()
                assert root.level == logging.WARNING
            finally:
                root.setLevel(original)

    async def test_uses_correct_setting_key(self) -> None:
        mock_cache = AsyncMock(spec=SettingsCache)
        mock_cache.get_str.return_value = "INFO"

        with patch(
            "syntara.settings.cache.settings_cache.get_runtime_settings",
            return_value=mock_cache,
        ):
            await apply_runtime_log_level()
            mock_cache.get_str.assert_called_once()
            call_args = mock_cache.get_str.call_args
            assert call_args[0][0] == "logging.log_level"
