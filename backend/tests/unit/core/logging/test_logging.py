"""Unit tests for core application logging configuration.

Tests cover:
- NexusLogRecordRenderer JSON serialization
- Application logging configuration (configure_app_logging)
- OTEL handler setup for root logger
- Formatter builders (JSON and text)
- Uvicorn logging configuration
"""

import json
import logging
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch
from uuid import uuid4

import pytest
from pydantic import SecretStr

from syntara.core.config.base import LogLevel
from syntara.core.logging.logging import (
    NexusLogRecordRenderer,
    build_nexus_formatter,
    build_nexus_json_formatter,
    build_nexus_text_formatter,
    configure_app_logging,
)


class TestNexusLogRecordRenderer:
    """Test suite for NexusJSONRenderer."""

    def test_basic_serialization(self) -> None:
        """Test basic JSON serialization with event field first."""
        renderer = NexusLogRecordRenderer()
        logger = Mock()
        event_dict = {
            "level": "info",
            "event": "test message",
            "timestamp": "2024-01-01T00:00:00",
        }

        result = renderer(logger, "info", event_dict)
        parsed = json.loads(result)

        assert parsed["event"] == "test message"
        assert parsed["level"] == "info"
        assert parsed["timestamp"] == "2024-01-01T00:00:00"

    def test_missing_event_key(self) -> None:
        """Test handling when 'event' key is missing."""
        renderer = NexusLogRecordRenderer()
        logger = Mock()
        event_dict = {
            "level": "info",
            "timestamp": "2024-01-01T00:00:00",
            "user_id": 123,
        }

        result = renderer(logger, "info", event_dict)
        parsed = json.loads(result)

        # Should not error and should contain all fields
        assert "level" in parsed
        assert "timestamp" in parsed
        assert "user_id" in parsed
        assert "event" not in parsed

    def test_non_serializable_objects(self) -> None:
        """Test handling of non-JSON-serializable objects using __repr__."""
        renderer = NexusLogRecordRenderer()
        logger = Mock()

        path_obj = Path("some_test_file.txt")
        uuid_obj = uuid4()

        event_dict = {
            "event": "test message",
            "path": path_obj,
            "uuid": uuid_obj,
            "custom_obj": object(),
        }

        result = renderer(logger, "info", event_dict)
        parsed = json.loads(result)

        assert parsed["event"] == "test message"
        assert parsed["path"] == repr(path_obj)
        assert parsed["uuid"] == repr(uuid_obj)
        assert "custom_obj" in parsed

    def test_nested_non_serializable_objects(self) -> None:
        """Test handling of nested structures with non-serializable objects."""
        renderer = NexusLogRecordRenderer()
        logger = Mock()

        path_obj = Path("base_file.txt")

        event_dict = {
            "event": "test message",
            "metadata": {
                "path": path_obj,
                "files": [Path("file1.txt"), Path("file2.txt")],
                "parameters": {
                    "base_path": path_obj,
                    "count": 5,
                },
            },
        }

        result = renderer(logger, "info", event_dict)
        parsed = json.loads(result)

        assert parsed["event"] == "test message"
        assert parsed["metadata"]["path"] == repr(path_obj)
        assert parsed["metadata"]["files"][0] == repr(Path("file1.txt"))
        assert parsed["metadata"]["files"][1] == repr(Path("file2.txt"))
        assert parsed["metadata"]["parameters"]["base_path"] == repr(path_obj)
        assert parsed["metadata"]["parameters"]["count"] == 5

    def test_preserves_json_serializable_types(self) -> None:
        """Test that JSON-serializable types are preserved as-is."""
        renderer = NexusLogRecordRenderer()
        logger = Mock()

        event_dict = {
            "event": "test message",
            "string": "hello",
            "integer": 42,
            "float": 3.14,
            "boolean": True,
            "null": None,
            "list": [1, 2, 3],
            "dict": {"key": "value"},
        }

        result = renderer(logger, "info", event_dict)
        parsed = json.loads(result)

        assert parsed["string"] == "hello"
        assert parsed["integer"] == 42
        assert parsed["float"] == pytest.approx(3.14)
        assert parsed["boolean"] is True
        assert parsed["null"] is None
        assert parsed["list"] == [1, 2, 3]
        assert parsed["dict"] == {"key": "value"}

    def test_empty_dict(self) -> None:
        """Test handling of empty event dictionary."""
        renderer = NexusLogRecordRenderer()
        logger = Mock()
        event_dict: dict[str, Any] = {}

        result = renderer(logger, "info", event_dict)
        parsed = json.loads(result)

        assert parsed == {}

    def test_tuple_serialization(self) -> None:
        """Test that tuples are converted to lists."""
        renderer = NexusLogRecordRenderer()
        logger = Mock()

        event_dict = {
            "event": "test message",
            "coordinates": (10, 20, 30),
        }

        result = renderer(logger, "info", event_dict)
        parsed = json.loads(result)

        assert parsed["coordinates"] == [10, 20, 30]

    def test_mixed_serializable_and_non_serializable(self) -> None:
        """Test mixed content with both serializable and non-serializable objects."""
        renderer = NexusLogRecordRenderer()
        logger = Mock()

        event_dict = {
            "event": "test message",
            "normal_string": "hello",
            "path_obj": Path("test_file.txt"),
            "normal_list": [1, 2, 3],
            "mixed_list": [1, Path("another_file.txt"), "string"],
        }

        result = renderer(logger, "info", event_dict)
        parsed = json.loads(result)

        assert parsed["normal_string"] == "hello"
        assert parsed["path_obj"] == repr(Path("test_file.txt"))
        assert parsed["normal_list"] == [1, 2, 3]
        assert parsed["mixed_list"] == [1, repr(Path("another_file.txt")), "string"]


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #


@pytest.fixture(autouse=True)
def _reset_root_logger() -> Generator[None, None, None]:
    """Reset root logger handlers and level between tests to ensure isolation."""
    root_logger = logging.getLogger()
    original_level = root_logger.level

    # Clean up handlers before test
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    yield

    # Clean up handlers after test
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Reset logger level to original
    root_logger.setLevel(original_level)


# ------------------------------------------------------------------ #
# Formatter Builder Tests
# ------------------------------------------------------------------ #


class TestFormatterBuilders:
    """Tests for formatter builder functions."""

    def test_build_nexus_formatter_returns_json_by_default(self, override_settings) -> None:
        """Test that build_nexus_formatter returns JSON formatter by default."""
        with override_settings(log_output_format="json"):
            formatter = build_nexus_formatter()

            # Should be ProcessorFormatter with JSON renderer
            assert formatter is not None
            assert hasattr(formatter, "processors")

    def test_build_nexus_formatter_returns_text_when_configured(self, override_settings) -> None:
        """Test that build_nexus_formatter returns text formatter when configured."""
        with override_settings(log_output_format="text"):
            formatter = build_nexus_formatter()

            # Should be ProcessorFormatter
            assert formatter is not None
            assert hasattr(formatter, "processors")

    def test_build_nexus_json_formatter_creates_processor_formatter(self) -> None:
        """Test that build_nexus_json_formatter creates a ProcessorFormatter."""
        formatter = build_nexus_json_formatter()

        assert formatter is not None
        assert hasattr(formatter, "processors")
        assert hasattr(formatter, "foreign_pre_chain")

    def test_build_nexus_text_formatter_creates_processor_formatter(self) -> None:
        """Test that build_nexus_text_formatter creates a ProcessorFormatter."""
        formatter = build_nexus_text_formatter()

        assert formatter is not None
        assert hasattr(formatter, "processors")
        assert hasattr(formatter, "foreign_pre_chain")


# ------------------------------------------------------------------ #
# configure_app_logging Tests
# ------------------------------------------------------------------ #


class TestConfigureAppLogging:
    """Tests for configure_app_logging function."""

    @patch("syntara.core.logging.logging.create_otel_handler")
    def test_adds_stdout_handler_to_root_logger(self, mock_create_otel: MagicMock, override_settings) -> None:
        """Test that configure_app_logging adds a stdout handler to root logger."""
        mock_create_otel.return_value = None

        with override_settings(otel_enabled=False):
            configure_app_logging()

            root_logger = logging.getLogger()

            # Should have exactly one handler (stdout)
            assert len(root_logger.handlers) == 1
            assert isinstance(root_logger.handlers[0], logging.StreamHandler)

    @patch("syntara.core.logging.logging.create_otel_handler")
    def test_clears_existing_handlers(self, mock_create_otel: MagicMock, override_settings) -> None:
        """Test that configure_app_logging clears existing handlers before adding new ones."""
        mock_create_otel.return_value = None

        # Record initial handler count, then add more
        root_logger = logging.getLogger()
        initial_count = len(root_logger.handlers)

        # Add two more handlers
        root_logger.addHandler(logging.StreamHandler())
        root_logger.addHandler(logging.StreamHandler())
        before_configure = len(root_logger.handlers)
        assert before_configure == initial_count + 2

        with override_settings(otel_enabled=False):
            configure_app_logging()

            # Should only have the new stdout handler (all previous cleared)
            assert len(root_logger.handlers) == 1

    @patch("syntara.core.logging.logging.create_otel_handler")
    @patch("syntara.core.logging.logging.settings")
    def test_sets_root_logger_level_to_fallback(self, mock_settings: MagicMock, mock_create_otel: MagicMock) -> None:
        """Test that configure_app_logging sets root logger level from settings.

        Note: Uses @patch instead of override_settings because this test checks
        that the module-level settings reference is read correctly, which requires
        mocking the entire settings object in the module's namespace.
        """
        mock_create_otel.return_value = None
        mock_settings.fallback_log_level = LogLevel.DEBUG
        mock_settings.otel_enabled = False

        configure_app_logging()

        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    @patch("syntara.core.logging.logging.create_otel_handler")
    def test_stdout_handler_has_formatter(self, mock_create_otel: MagicMock, override_settings) -> None:
        """Test that stdout handler has a formatter configured."""
        mock_create_otel.return_value = None

        with override_settings(otel_enabled=False):
            configure_app_logging()

            root_logger = logging.getLogger()
            stdout_handler = root_logger.handlers[0]

            assert stdout_handler.formatter is not None

    @patch("syntara.core.logging.otel_handlers.OTLPLogExporter")
    def test_adds_otel_handler_when_enabled(self, mock_exporter_class: MagicMock, override_settings) -> None:
        """Test that configure_app_logging adds OTEL handler when enabled."""
        mock_exporter_instance = MagicMock()
        mock_exporter_class.return_value = mock_exporter_instance

        with override_settings(
            otel_enabled=True,
            otel_endpoint="https://otlp.example.com/v1/logs",
            otel_service_name="nexus-test",
            fallback_log_level="INFO",
            log_output_format="json",
        ):
            configure_app_logging()

        root_logger = logging.getLogger()

        # Should have 2 handlers: stdout + OTEL
        assert len(root_logger.handlers) == 2

        # Verify handler types
        handler_types = {type(h).__name__ for h in root_logger.handlers}
        assert "StreamHandler" in handler_types
        assert "LoggingHandler" in handler_types

    @patch("syntara.core.logging.logging.create_otel_handler")
    @patch("syntara.core.logging.logging.logging.getLogger")
    @patch("syntara.core.logging.logging.settings")
    def test_logs_otel_configuration_when_enabled(
        self,
        mock_settings: MagicMock,
        mock_get_logger: MagicMock,
        mock_create_otel: MagicMock,
    ) -> None:
        """Test that configure_app_logging logs when OTEL is configured.

        Note: Uses @patch for settings instead of override_settings because the test
        needs to verify that the specific settings values are logged correctly, and
        @patch ensures the mocked values are seen by the logging code.
        """
        # Mock OTEL handler
        mock_handler = MagicMock()
        mock_create_otel.return_value = mock_handler

        # Mock logger
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        # Mock settings
        mock_settings.otel_enabled = True
        mock_settings.otel_endpoint = "https://otlp.example.com/v1/logs"
        mock_settings.otel_service_name = "nexus-test"
        mock_settings.fallback_log_level = LogLevel.INFO
        mock_settings.log_output_format = "json"

        configure_app_logging()

        # Verify info log was emitted about OTEL configuration
        info_calls = [call for call in mock_logger.info.call_args_list if call[0][0] == "logging.root_otel_configured"]
        assert len(info_calls) >= 1
        log_call = info_calls[0]
        assert log_call[1]["extra"]["endpoint"] == "https://otlp.example.com/v1/logs"
        assert log_call[1]["extra"]["service_name"] == "nexus-test"

    @patch("syntara.core.logging.logging.create_otel_handler")
    def test_does_not_add_otel_handler_when_disabled(self, mock_create_otel: MagicMock, override_settings) -> None:
        """Test that configure_app_logging does not add OTEL handler when disabled."""
        mock_create_otel.return_value = None

        with override_settings(otel_enabled=False):
            configure_app_logging()

            root_logger = logging.getLogger()

            # Should only have stdout handler
            assert len(root_logger.handlers) == 1
            assert isinstance(root_logger.handlers[0], logging.StreamHandler)

    @patch("syntara.core.logging.logging.create_otel_handler")
    def test_configures_structlog(self, mock_create_otel: MagicMock, override_settings) -> None:
        """Test that configure_app_logging configures structlog processors."""
        mock_create_otel.return_value = None

        with override_settings(otel_enabled=False):
            configure_app_logging()

            # Verify structlog is configured by attempting to use it
            import structlog

            logger = structlog.get_logger()
            # Should not raise
            assert logger is not None

    @patch("syntara.core.logging.logging.create_otel_handler")
    def test_otel_handler_created_with_correct_logger_name(self, mock_create: MagicMock, override_settings) -> None:
        """Test that OTEL handler is created for root logger."""
        # Create a mock handler with proper level attribute
        mock_handler = MagicMock()
        mock_handler.level = logging.INFO
        mock_create.return_value = mock_handler

        with override_settings(
            otel_enabled=True,
            otel_endpoint="https://otlp.example.com/v1/logs",
            otel_service_name="nexus-test",
            fallback_log_level="INFO",
            log_output_format="json",
        ):
            configure_app_logging()

        # Verify create_otel_handler was called
        mock_create.assert_called_once_with()

    @patch("syntara.core.logging.otel_handlers.OTLPLogExporter")
    def test_otel_handler_with_api_key_authentication(self, mock_exporter_class: MagicMock, override_settings) -> None:
        """Test that OTEL handler is configured with API key authentication."""
        mock_exporter_instance = MagicMock()
        mock_exporter_class.return_value = mock_exporter_instance

        api_key = "test-api-key-12345"

        with override_settings(
            otel_enabled=True,
            otel_endpoint="https://otlp.example.com/v1/logs",
            otel_service_name="nexus-test",
            otel_api_key=SecretStr(api_key),
            otel_auth_header_name="X-API-Key",
            otel_ca_cert_file=None,
            otel_client_cert_file=None,
            otel_client_key_file=None,
            fallback_log_level="INFO",
            log_output_format="json",
        ):
            configure_app_logging()

        # Verify OTLPLogExporter was called with authentication headers
        mock_exporter_class.assert_called_once()
        call_kwargs = mock_exporter_class.call_args[1]

        assert call_kwargs["endpoint"] == "https://otlp.example.com/v1/logs"
        assert call_kwargs["headers"] == {"X-API-Key": f"Bearer {api_key}"}

    @patch("syntara.core.logging.otel_handlers.OTLPLogExporter")
    def test_otel_handler_with_mtls_authentication(self, mock_exporter_class: MagicMock, override_settings) -> None:
        """Test that OTEL handler is configured with mTLS certificate files."""
        mock_exporter_instance = MagicMock()
        mock_exporter_class.return_value = mock_exporter_instance

        with override_settings(
            otel_enabled=True,
            otel_endpoint="https://otlp.example.com/v1/logs",
            otel_service_name="nexus-test",
            otel_ca_cert_file="/etc/ssl/ca.crt",
            otel_client_cert_file="/etc/ssl/client.crt",
            otel_client_key_file="/etc/ssl/client.key",
            otel_api_key=None,
            fallback_log_level="INFO",
            log_output_format="json",
        ):
            configure_app_logging()

        # Verify OTLPLogExporter was called with certificate files
        mock_exporter_class.assert_called_once()
        call_kwargs = mock_exporter_class.call_args[1]

        assert call_kwargs["endpoint"] == "https://otlp.example.com/v1/logs"
        assert call_kwargs["certificate_file"] == "/etc/ssl/ca.crt"
        assert call_kwargs["client_certificate_file"] == "/etc/ssl/client.crt"
        assert call_kwargs["client_key_file"] == "/etc/ssl/client.key"
