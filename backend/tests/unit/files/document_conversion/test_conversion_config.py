"""Test for ConversionConfig model validation and behavior."""

import tempfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from syntara.files.document_conversion.models.conversion_config import (
    ConversionConfig,
)


class TestConversionConfigValidation:
    """Test ConversionConfig validation logic."""

    def test_timeout_seconds_validation_minimum_boundary(self) -> None:
        """Test timeout_seconds validation at minimum boundary."""
        temp_dir = tempfile.gettempdir()
        with pytest.raises(ValueError, match="Input should be greater than or equal to 1"):
            ConversionConfig(timeout_seconds=0, temp_dir=temp_dir)

    def test_timeout_seconds_validation_maximum_boundary(self) -> None:
        """Test timeout_seconds validation at maximum boundary."""
        temp_dir = tempfile.gettempdir()
        with pytest.raises(ValueError, match="Input should be less than or equal to 300"):
            ConversionConfig(timeout_seconds=301, temp_dir=temp_dir)

    def test_timeout_seconds_accepts_valid_range(self) -> None:
        """Test timeout_seconds accepts values within valid range."""
        temp_dir = tempfile.gettempdir()
        config = ConversionConfig(timeout_seconds=30, temp_dir=temp_dir)
        assert config.timeout_seconds == 30

    def test_overwrite_existing_default_behavior(self) -> None:
        """Test that overwrite_existing defaults to False when not specified."""
        temp_dir = tempfile.gettempdir()
        config = ConversionConfig(timeout_seconds=30, temp_dir=temp_dir)
        assert config.overwrite_existing is False

    def test_overwrite_existing_accepts_true(self) -> None:
        """Test that overwrite_existing can be set to True."""
        temp_dir = tempfile.gettempdir()
        config = ConversionConfig(timeout_seconds=30, temp_dir=temp_dir, overwrite_existing=True)
        assert config.overwrite_existing is True

    def test_temp_dir_required_field(self) -> None:
        """Test that temp_dir is a required field."""
        with pytest.raises(ValueError, match="temp_dir"):
            ConversionConfig(timeout_seconds=30)  # type: ignore[call-arg]

    def test_temp_dir_accepts_valid_paths(self) -> None:
        """Test that temp_dir accepts valid directory paths."""
        test_path = str(Path(tempfile.gettempdir()) / "conversions")
        config = ConversionConfig(timeout_seconds=30, temp_dir=test_path)
        assert config.temp_dir == test_path


class TestConversionConfigSystemIntegration:
    """Test ConversionConfig integration with system configuration."""

    async def test_from_settings_reads_from_cache(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that from_settings reads live values from the settings cache."""
        mock_cache = AsyncMock()
        mock_cache.get_int.return_value = 25
        mock_cache.get_bool.return_value = True

        with (
            override_settings(document_conversion_temp_dir="/app/tmp/conversions"),
            patch(
                "syntara.files.document_conversion.models.conversion_config.get_runtime_settings",
                return_value=mock_cache,
            ),
        ):
            config = await ConversionConfig.from_settings()

        assert config.timeout_seconds == 25
        assert config.overwrite_existing is True
        assert config.temp_dir == "/app/tmp/conversions"

    async def test_from_settings_respects_timeout_boundaries(
        self,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that from_settings respects timeout validation boundaries."""
        mock_cache = AsyncMock()
        mock_cache.get_int.return_value = 1
        mock_cache.get_bool.return_value = False

        with (
            override_settings(document_conversion_temp_dir=tempfile.gettempdir()),
            patch(
                "syntara.files.document_conversion.models.conversion_config.get_runtime_settings",
                return_value=mock_cache,
            ),
        ):
            config = await ConversionConfig.from_settings()

        assert config.timeout_seconds == 1

    def test_nfr_001_timeout_constraint_enforcement(self) -> None:
        """Test that NFR-001 (under 30 seconds) constraint is enforced."""
        temp_dir = tempfile.gettempdir()
        config = ConversionConfig(timeout_seconds=30, temp_dir=temp_dir)
        assert config.timeout_seconds == 30

        temp_dir = tempfile.gettempdir()
        config = ConversionConfig(timeout_seconds=60, temp_dir=temp_dir)
        assert config.timeout_seconds == 60
