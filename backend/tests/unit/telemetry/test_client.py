"""Unit tests for TelemetryClientRegistry."""

from unittest.mock import MagicMock, patch

import pytest

from syntara.telemetry.client import TelemetryClientRegistry
from syntara.telemetry.events.workflow_execution import WorkflowExecutionStartEvent


class TestTelemetryClientRegistry:
    """Tests for TelemetryClientRegistry lifecycle."""

    def test_initial_state_not_initialized(self):
        registry = TelemetryClientRegistry()
        assert registry.is_initialized() is False

    def test_get_client_before_init_raises(self):
        registry = TelemetryClientRegistry()
        with pytest.raises(RuntimeError, match="not initialized"):
            registry.get_client()

    @patch("syntara.telemetry.client.segment_analytics")
    def test_initialize_creates_client(self, mock_segment):
        mock_client = MagicMock()
        mock_segment.Client.return_value = mock_client

        registry = TelemetryClientRegistry()
        registry.initialize(write_key="test-key")
        assert registry.is_initialized() is True

    @patch("syntara.telemetry.client.logger")
    @patch("syntara.telemetry.client.segment_analytics")
    def test_initialize_idempotent(self, mock_segment, mock_logger):
        mock_segment.Client.return_value = MagicMock()

        registry = TelemetryClientRegistry()
        registry.initialize(write_key="test-key")
        registry.initialize(write_key="other-key")

        assert mock_segment.Client.call_count == 1
        mock_logger.warning.assert_called_once_with("TelemetryClientRegistry already initialized")

    @patch("syntara.telemetry.client.segment_analytics")
    def test_flush_calls_client_flush(self, mock_segment):
        mock_client = MagicMock()
        mock_segment.Client.return_value = mock_client

        registry = TelemetryClientRegistry()
        registry.initialize(write_key="test-key")
        registry.flush()

        mock_client.flush.assert_called_once()
        assert registry.is_initialized() is True

    def test_flush_when_not_initialized(self):
        registry = TelemetryClientRegistry()
        registry.flush()  # Should not raise

    @patch("syntara.telemetry.client.segment_analytics")
    def test_send_event_calls_track(self, mock_segment):
        mock_client = MagicMock()
        mock_segment.Client.return_value = mock_client

        registry = TelemetryClientRegistry()
        registry.initialize(
            write_key="test-key",
            entitlement_id="test-user",
            anonymous_id="anon-id-123",
        )

        event = WorkflowExecutionStartEvent(
            workflow_execution_id="test-correlation-id",
            entitlement_id="test-user",
        )

        registry.send_event(event)

        raw = event.to_segment_event()["properties"]
        expected_properties = dict(raw) if isinstance(raw, dict) else {}
        expected_properties["entitlement_id"] = "test-user"

        raw_context = event.to_segment_event().get("context", {})
        expected_context = dict(raw_context) if isinstance(raw_context, dict) else {}

        mock_client.track.assert_called_once_with(
            anonymous_id="anon-id-123",
            event="workflow_execution_start",
            properties=expected_properties,
            context=expected_context,
        )

    @patch("syntara.telemetry.client.logger")
    @patch("syntara.telemetry.client.segment_analytics")
    def test_send_event_fire_and_forget(self, mock_segment, mock_logger):
        mock_client = MagicMock()
        mock_client.track.side_effect = RuntimeError("network error")
        mock_segment.Client.return_value = mock_client

        registry = TelemetryClientRegistry()
        registry.initialize(write_key="test-key")

        event = WorkflowExecutionStartEvent(
            workflow_execution_id="test-id",
            entitlement_id="",
        )

        # Should not raise
        registry.send_event(event)
        mock_logger.exception.assert_called_once()

    def test_default_entitlement_id(self):
        registry = TelemetryClientRegistry()
        assert registry.entitlement_id == ""

    def test_error_handler_logs_warning(self):
        with patch("syntara.telemetry.client.logger") as mock_logger:
            TelemetryClientRegistry._error_handler(RuntimeError("test"), [{"item": 1}])
            mock_logger.warning.assert_called_once()
