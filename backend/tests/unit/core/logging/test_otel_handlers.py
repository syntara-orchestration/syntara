"""Unit tests for OpenTelemetry logging handler creation and management.

Tests cover:
- create_otel_handler: Handler factory with authentication support
- create_otlp_exporter: Exporter factory with authentication support
- flush_otel_handler: Flushing and cleanup of OTLP handlers
- _create_logger_provider: Logger provider with resource identification
- Edge cases: no authentication, error handling
"""

import logging
from unittest.mock import MagicMock, Mock, patch

from pydantic import SecretStr

from syntara.core.logging.otel_handlers import (
    create_otel_handler,
    flush_otel_handler,
)

# ------------------------------------------------------------------ #
# create_otel_handler Tests
# ------------------------------------------------------------------ #


class TestCreateOtelHandler:
    """Tests for create_otel_handler function."""

    def test_returns_none_when_otel_disabled(self, override_settings) -> None:
        """Test that create_otel_handler returns None when OTLP is disabled."""
        with override_settings(otel_enabled=False):
            handler = create_otel_handler()

            assert handler is None

    @patch("syntara.core.logging.otel_handlers.OTLPLogExporter")
    def test_returns_logging_handler_when_enabled(self, mock_exporter: MagicMock, override_settings) -> None:
        """Test that create_otel_handler returns a LoggingHandler when enabled."""
        mock_exporter.return_value = MagicMock()

        with override_settings(
            otel_enabled=True,
            otel_endpoint="https://otlp.example.com/v1/logs",
            otel_service_name="nexus-test",
        ):
            handler = create_otel_handler()

            assert handler is not None
            assert handler.__class__.__name__ == "LoggingHandler"

    @patch("syntara.core.logging.otel_handlers.OTLPLogExporter")
    def test_handler_level_set_to_notset(self, mock_exporter: MagicMock, override_settings) -> None:
        """Test that created handler has level set to NOTSET."""
        mock_exporter.return_value = MagicMock()

        with override_settings(
            otel_enabled=True,
            otel_endpoint="https://otlp.example.com/v1/logs",
            otel_service_name="nexus-test",
        ):
            handler = create_otel_handler()

            assert handler is not None
            assert handler.level == logging.NOTSET

    @patch("syntara.core.logging.otel_handlers.OTLPLogExporter")
    def test_creates_handler_with_api_key_authentication(self, mock_exporter: MagicMock, override_settings) -> None:
        """Test that handler is created with API key authentication."""
        mock_exporter.return_value = MagicMock()

        api_key = "test-api-key-12345"

        with override_settings(
            otel_enabled=True,
            otel_endpoint="https://otlp.example.com/v1/logs",
            otel_service_name="nexus-test",
            otel_api_key=SecretStr(api_key),
            otel_auth_header_name="X-API-Key",
        ):
            handler = create_otel_handler()

            assert handler is not None

            # Verify OTLPLogExporter was called with authentication headers
            mock_exporter.assert_called_once()
            call_kwargs = mock_exporter.call_args[1]

            assert call_kwargs["endpoint"] == "https://otlp.example.com/v1/logs"
            assert call_kwargs["headers"] == {"X-API-Key": f"Bearer {api_key}"}
            assert call_kwargs["certificate_file"] is None
            assert call_kwargs["client_certificate_file"] is None
            assert call_kwargs["client_key_file"] is None

    @patch("syntara.core.logging.otel_handlers.OTLPLogExporter")
    def test_creates_handler_with_mtls_authentication(self, mock_exporter: MagicMock, override_settings) -> None:
        """Test that handler is created with mTLS certificate authentication."""
        mock_exporter.return_value = MagicMock()

        with override_settings(
            otel_enabled=True,
            otel_endpoint="https://otlp.example.com/v1/logs",
            otel_service_name="nexus-test",
            otel_ca_cert_file="/etc/ssl/ca.crt",
            otel_client_cert_file="/etc/ssl/client.crt",
            otel_client_key_file="/etc/ssl/client.key",
        ):
            handler = create_otel_handler()

            assert handler is not None

            # Verify OTLPLogExporter was called with certificate files
            mock_exporter.assert_called_once()
            call_kwargs = mock_exporter.call_args[1]

            assert call_kwargs["endpoint"] == "https://otlp.example.com/v1/logs"
            assert call_kwargs["headers"] is None
            assert call_kwargs["certificate_file"] == "/etc/ssl/ca.crt"
            assert call_kwargs["client_certificate_file"] == "/etc/ssl/client.crt"
            assert call_kwargs["client_key_file"] == "/etc/ssl/client.key"

    @patch("syntara.core.logging.otel_handlers.logger")
    @patch("syntara.core.logging.otel_handlers.OTLPLogExporter")
    def test_warns_when_no_authentication_configured(
        self, mock_exporter: MagicMock, mock_logger: MagicMock, override_settings
    ) -> None:
        """Test that warning is logged when OTLP endpoint has no authentication."""
        mock_exporter.return_value = MagicMock()

        with override_settings(
            otel_enabled=True,
            otel_endpoint="http://localhost:4318/v1/logs",
            otel_service_name="nexus-test",
        ):
            create_otel_handler()

            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            warning_call = mock_logger.warning.call_args
            assert warning_call[0][0] == "otel.handler.no_authentication"
            assert warning_call[1]["endpoint"] == "http://localhost:4318/v1/logs"

    @patch("syntara.core.logging.otel_handlers.OTLPLogExporter")
    def test_includes_service_name_in_resource(self, mock_exporter: MagicMock, override_settings) -> None:
        """Test that logger provider includes service name in resource."""
        mock_exporter.return_value = MagicMock()

        with override_settings(
            otel_enabled=True,
            otel_endpoint="https://otlp.example.com/v1/logs",
            otel_service_name="nexus-test-service",
        ):
            handler = create_otel_handler()

            assert handler is not None
            # Verify service name is in the resource (access via _logger_provider)
            resource_attrs = handler._logger_provider._resource.attributes  # type: ignore[attr-defined]
            assert resource_attrs.get("service.name") == "nexus-test-service"

    @patch("syntara.core.logging.otel_handlers.OTLPLogExporter")
    def test_includes_service_instance_id_in_resource(self, mock_exporter: MagicMock, override_settings) -> None:
        """Test that logger provider includes service instance ID (hostname) in resource."""
        import os

        mock_exporter.return_value = MagicMock()

        with override_settings(
            otel_enabled=True,
            otel_endpoint="https://otlp.example.com/v1/logs",
            otel_service_name="nexus-test",
        ):
            handler = create_otel_handler()

            assert handler is not None
            # Verify service instance ID is in the resource (access via _logger_provider)
            resource_attrs = handler._logger_provider._resource.attributes  # type: ignore[attr-defined]
            assert resource_attrs.get("service.instance.id") == os.uname().nodename


# ------------------------------------------------------------------ #
# flush_otel_handler Tests
# ------------------------------------------------------------------ #


class TestFlushOtelHandler:
    """Tests for flush_otel_handler function."""

    def test_flushes_handler_with_logger_provider(self) -> None:
        """Test that handlers with logger_provider attribute are flushed."""
        # Create a logger and mock OTLP handler
        test_logger = logging.getLogger("test.flush.logger")
        mock_handler = Mock()
        mock_handler.logger_provider = Mock()
        mock_handler.flush = Mock()
        mock_handler.logger_provider.force_flush = Mock()

        test_logger.addHandler(mock_handler)

        try:
            flush_otel_handler(test_logger)

            # Verify both flush methods were called
            mock_handler.flush.assert_called_once()
            mock_handler.logger_provider.force_flush.assert_called_once()
        finally:
            test_logger.removeHandler(mock_handler)

    def test_skips_handler_without_logger_provider(self) -> None:
        """Test that handlers without logger_provider attribute are skipped."""
        # Create a logger with a standard StreamHandler (no logger_provider)
        test_logger = logging.getLogger("test.skip.logger")
        stream_handler = logging.StreamHandler()
        test_logger.addHandler(stream_handler)

        try:
            # Should not raise even though handler has no logger_provider
            flush_otel_handler(test_logger)
        finally:
            test_logger.removeHandler(stream_handler)

    def test_handles_flush_exception_gracefully(self) -> None:
        """Test that flush exceptions are caught and logged without raising."""
        test_logger = logging.getLogger("test.exception.logger")
        mock_handler = Mock()
        mock_handler.logger_provider = Mock()
        mock_handler.flush = Mock(side_effect=Exception("Flush failed"))

        test_logger.addHandler(mock_handler)

        try:
            with patch("syntara.core.logging.otel_handlers.logger") as mock_logger:
                # Should not raise
                flush_otel_handler(test_logger)

                # Verify warning was logged
                mock_logger.warning.assert_called_once()
                warning_call = mock_logger.warning.call_args
                assert warning_call[0][0] == "otel.handler.flush_failed"
                assert warning_call[1]["logger_name"] == test_logger.name
        finally:
            test_logger.removeHandler(mock_handler)

    def test_handles_force_flush_exception_gracefully(self) -> None:
        """Test that force_flush exceptions are caught and logged."""
        test_logger = logging.getLogger("test.force_flush.exception.logger")
        mock_handler = Mock()
        mock_handler.logger_provider = Mock()
        mock_handler.flush = Mock()
        mock_handler.logger_provider.force_flush = Mock(side_effect=Exception("Force flush failed"))

        test_logger.addHandler(mock_handler)

        try:
            with patch("syntara.core.logging.otel_handlers.logger") as mock_logger:
                # Should not raise
                flush_otel_handler(test_logger)

                # Verify warning was logged
                mock_logger.warning.assert_called_once()
        finally:
            test_logger.removeHandler(mock_handler)

    def test_logs_success_message(self) -> None:
        """Test that successful flush logs an info message."""
        test_logger = logging.getLogger("test.success.logger")
        mock_handler = Mock()
        mock_handler.logger_provider = Mock()
        mock_handler.flush = Mock()
        mock_handler.logger_provider.force_flush = Mock()

        test_logger.addHandler(mock_handler)

        try:
            with patch("syntara.core.logging.otel_handlers.logger") as mock_logger:
                flush_otel_handler(test_logger)

                # Verify info log was emitted
                mock_logger.info.assert_called_once()
                info_call = mock_logger.info.call_args
                assert info_call[0][0] == "otel.handler.flushed"
                assert info_call[1]["logger_name"] == test_logger.name
        finally:
            test_logger.removeHandler(mock_handler)

    def test_flushes_multiple_otel_handlers(self) -> None:
        """Test that multiple OTLP handlers on same logger are all flushed."""
        test_logger = logging.getLogger("test.multiple.logger")

        # Add two mock OTLP handlers
        mock_handler1 = Mock()
        mock_handler1.logger_provider = Mock()
        mock_handler1.flush = Mock()
        mock_handler1.logger_provider.force_flush = Mock()

        mock_handler2 = Mock()
        mock_handler2.logger_provider = Mock()
        mock_handler2.flush = Mock()
        mock_handler2.logger_provider.force_flush = Mock()

        test_logger.addHandler(mock_handler1)
        test_logger.addHandler(mock_handler2)

        try:
            flush_otel_handler(test_logger)

            # Verify both handlers were flushed
            mock_handler1.flush.assert_called_once()
            mock_handler1.logger_provider.force_flush.assert_called_once()
            mock_handler2.flush.assert_called_once()
            mock_handler2.logger_provider.force_flush.assert_called_once()
        finally:
            test_logger.removeHandler(mock_handler1)
            test_logger.removeHandler(mock_handler2)

    def test_continues_flushing_after_one_handler_fails(self) -> None:
        """Test that flush continues to other handlers even if one fails."""
        test_logger = logging.getLogger("test.partial_failure.logger")

        # First handler fails
        mock_handler1 = Mock()
        mock_handler1.logger_provider = Mock()
        mock_handler1.flush = Mock(side_effect=Exception("Handler 1 failed"))

        # Second handler succeeds
        mock_handler2 = Mock()
        mock_handler2.logger_provider = Mock()
        mock_handler2.flush = Mock()
        mock_handler2.logger_provider.force_flush = Mock()

        test_logger.addHandler(mock_handler1)
        test_logger.addHandler(mock_handler2)

        try:
            with patch("syntara.core.logging.otel_handlers.logger"):
                flush_otel_handler(test_logger)

                # Verify second handler was still flushed despite first failure
                mock_handler2.flush.assert_called_once()
                mock_handler2.logger_provider.force_flush.assert_called_once()
        finally:
            test_logger.removeHandler(mock_handler1)
            test_logger.removeHandler(mock_handler2)

    def test_handles_mixed_handler_types(self) -> None:
        """Test flushing logger with both OTLP and regular handlers."""
        test_logger = logging.getLogger("test.mixed.logger")

        # Add regular StreamHandler (no logger_provider)
        stream_handler = logging.StreamHandler()

        # Add mock OTLP handler
        mock_otlp_handler = Mock()
        mock_otlp_handler.logger_provider = Mock()
        mock_otlp_handler.flush = Mock()
        mock_otlp_handler.logger_provider.force_flush = Mock()

        test_logger.addHandler(stream_handler)
        test_logger.addHandler(mock_otlp_handler)

        try:
            flush_otel_handler(test_logger)

            # Only OTLP handler should be flushed
            mock_otlp_handler.flush.assert_called_once()
            mock_otlp_handler.logger_provider.force_flush.assert_called_once()
        finally:
            test_logger.removeHandler(stream_handler)
            test_logger.removeHandler(mock_otlp_handler)

    def test_handles_logger_with_no_handlers(self) -> None:
        """Test that flush handles logger with no handlers gracefully."""
        test_logger = logging.getLogger("test.empty.logger")

        # Remove all handlers
        for handler in test_logger.handlers[:]:
            test_logger.removeHandler(handler)

        # Should not raise
        flush_otel_handler(test_logger)
