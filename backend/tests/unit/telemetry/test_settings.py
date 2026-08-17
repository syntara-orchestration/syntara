"""Unit tests for TelemetrySettings."""

from syntara.core.config.base import Settings, TelemetrySettings


class TestTelemetrySettings:
    """Tests for TelemetrySettings configuration."""

    def test_default_segment_endpoint(self):
        settings = TelemetrySettings()
        assert str(settings.segment_endpoint) == "https://api.segment.io/"

    def test_telemetry_settings_in_composite(self):
        """TelemetrySettings is part of the composite Settings class."""
        assert issubclass(Settings, TelemetrySettings)

    def test_segment_write_key_is_secret(self):
        """segment_write_key should be SecretStr to prevent accidental logging."""
        settings = TelemetrySettings()
        assert "SecretStr" in type(settings.segment_write_key).__name__
