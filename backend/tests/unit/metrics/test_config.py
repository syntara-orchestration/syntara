"""Unit tests for MetricsSettings configuration."""

import pytest

from syntara.core.config.base import Settings


class TestMetricsSettings:
    """Tests for MetricsSettings configuration."""

    def test_metrics_defaults(self) -> None:
        """Test default metrics configuration values."""
        settings = Settings()
        assert settings.metrics_retention_seconds == 3600
        assert settings.metrics_max_records == 100_000
        assert settings.metrics_enabled is True
        assert settings.metrics_openmetrics_enabled is True

    def test_metrics_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test metrics settings can be configured via environment."""
        monkeypatch.setenv("APP_METRICS_RETENTION_SECONDS", "3600")
        monkeypatch.setenv("APP_METRICS_MAX_RECORDS", "500000")
        monkeypatch.setenv("APP_METRICS_ENABLED", "false")
        monkeypatch.setenv("APP_METRICS_OPENMETRICS_ENABLED", "false")
        settings = Settings()
        assert settings.metrics_retention_seconds == 3600
        assert settings.metrics_max_records == 500000
        assert settings.metrics_enabled is False
        assert settings.metrics_openmetrics_enabled is False

    def test_metrics_retention_allows_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Retention of 0 is valid (no retention / immediate expiry)."""
        monkeypatch.setenv("APP_METRICS_RETENTION_SECONDS", "0")
        settings = Settings()
        assert settings.metrics_retention_seconds == 0

    def test_metrics_max_records_validation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """max_records must be at least 1."""
        monkeypatch.setenv("APP_METRICS_MAX_RECORDS", "0")
        with pytest.raises(ValueError, match="greater than or equal to 1"):
            Settings()
