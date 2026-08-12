"""Unit tests for execution streaming WebSocket handler."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.core.websocket.close_codes import UNSUPPORTED_DATA
from syntara.workflows.ws.execution_streaming import on_connect_executions


@pytest.fixture
def mock_execution_streaming_service() -> MagicMock:
    """Create a mock execution streaming service."""
    service = MagicMock()
    service.stream_events_to_websocket = AsyncMock()
    return service


class TestOnConnectExecutions:
    """Test cases for on_connect_executions WebSocket handler."""

    async def test_invalid_execution_id_closes_connection(self, mock_websocket: MagicMock) -> None:
        """Test that invalid UUID in path closes connection with error."""
        # Setup: Invalid UUID in path
        mock_websocket.url.path = "/ws/workflows/v1/executions/not-a-uuid"
        mock_websocket.query_params = {}

        # Execute
        await on_connect_executions(mock_websocket, "test-conn-1")

        # Verify: Connection closed with appropriate error
        mock_websocket.close.assert_called_once_with(code=UNSUPPORTED_DATA, reason="Invalid execution ID")

    async def test_invalid_replay_format_closes_connection(
        self,
        mock_websocket: MagicMock,
    ) -> None:
        """Test that invalid replay format closes connection with validation error."""
        # Setup: Valid UUID, invalid replay format
        execution_id = uuid4()
        mock_websocket.url.path = f"/ws/workflows/v1/executions/{execution_id}"
        mock_websocket.query_params = {"replay": "invalid-format"}

        # Execute
        await on_connect_executions(mock_websocket, "test-conn-1")

        # Verify: Connection closed with validation error
        mock_websocket.close.assert_called_once()
        call_args = mock_websocket.close.call_args
        assert call_args.kwargs["code"] == UNSUPPORTED_DATA
        assert "timestamp-sequence" in call_args.kwargs["reason"]

    async def test_valid_parameters_calls_streaming_service(
        self,
        mock_websocket: MagicMock,
        mock_execution_streaming_service: MagicMock,
    ) -> None:
        """Test that valid parameters delegate to streaming service."""
        # Setup: Valid UUID and query params
        execution_id = uuid4()
        mock_websocket.url.path = f"/ws/workflows/v1/executions/{execution_id}"
        mock_websocket.query_params = {"replay": "1234567890-5"}
        mock_websocket.app.state.execution_streaming_service = mock_execution_streaming_service

        # Execute
        await on_connect_executions(mock_websocket, "test-conn-1")

        # Verify: Streaming service called with validated parameters
        mock_execution_streaming_service.stream_events_to_websocket.assert_called_once_with(
            websocket=mock_websocket,
            execution_id=execution_id,
            replay="1234567890-5",
            connection_id="test-conn-1",
            user_id=None,
            username=None,
            actor_type=None,
        )
        # Connection should NOT be closed for valid params
        mock_websocket.close.assert_not_called()

    async def test_no_replay_parameter(
        self,
        mock_websocket: MagicMock,
        mock_execution_streaming_service: MagicMock,
    ) -> None:
        """Test that missing replay parameter uses None (live streaming only)."""
        # Setup: Valid UUID, no query params
        execution_id = uuid4()
        mock_websocket.url.path = f"/ws/workflows/v1/executions/{execution_id}"
        mock_websocket.query_params = {}  # Empty query params
        mock_websocket.app.state.execution_streaming_service = mock_execution_streaming_service

        # Execute
        await on_connect_executions(mock_websocket, "test-conn-1")

        # Verify: None used (live streaming only)
        mock_execution_streaming_service.stream_events_to_websocket.assert_called_once_with(
            websocket=mock_websocket,
            execution_id=execution_id,
            replay=None,  # No replay
            connection_id="test-conn-1",
            user_id=None,
            username=None,
            actor_type=None,
        )

    async def test_replay_zero_from_beginning(
        self,
        mock_websocket: MagicMock,
        mock_execution_streaming_service: MagicMock,
    ) -> None:
        """Test that replay='0' is accepted (replay from beginning)."""
        # Setup: Valid UUID, replay='0'
        execution_id = uuid4()
        mock_websocket.url.path = f"/ws/workflows/v1/executions/{execution_id}"
        mock_websocket.query_params = {"replay": "0"}
        mock_websocket.app.state.execution_streaming_service = mock_execution_streaming_service

        # Execute
        await on_connect_executions(mock_websocket, "test-conn-1")

        # Verify: '0' passed through
        mock_execution_streaming_service.stream_events_to_websocket.assert_called_once()
        call_args = mock_execution_streaming_service.stream_events_to_websocket.call_args
        assert call_args.kwargs["replay"] == "0"

    async def test_valid_timestamp_sequence_format(
        self,
        mock_websocket: MagicMock,
        mock_execution_streaming_service: MagicMock,
    ) -> None:
        """Test that valid timestamp-sequence format is accepted."""
        # Setup: Valid stream ID format
        execution_id = uuid4()
        mock_websocket.url.path = f"/ws/workflows/v1/executions/{execution_id}"
        mock_websocket.query_params = {"replay": "1691431234567-42"}
        mock_websocket.app.state.execution_streaming_service = mock_execution_streaming_service

        # Execute
        await on_connect_executions(mock_websocket, "test-conn-1")

        # Verify: Valid format passed through
        mock_execution_streaming_service.stream_events_to_websocket.assert_called_once()
        call_args = mock_execution_streaming_service.stream_events_to_websocket.call_args
        assert call_args.kwargs["replay"] == "1691431234567-42"

    async def test_extra_query_params_ignored(
        self,
        mock_websocket: MagicMock,
        mock_execution_streaming_service: MagicMock,
    ) -> None:
        """Test that extra query parameters are ignored (no error)."""
        # Setup: Valid params plus extra unknown param
        execution_id = uuid4()
        mock_websocket.url.path = f"/ws/workflows/v1/executions/{execution_id}"
        mock_websocket.query_params = {"replay": "0", "unknown_param": "should_be_ignored"}
        mock_websocket.app.state.execution_streaming_service = mock_execution_streaming_service

        # Execute
        await on_connect_executions(mock_websocket, "test-conn-1")

        # Verify: No error, streaming proceeds normally
        mock_execution_streaming_service.stream_events_to_websocket.assert_called_once()
        mock_websocket.close.assert_not_called()
