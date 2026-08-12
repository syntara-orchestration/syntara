"""Unit tests for streaming WebSocket adaptor handler."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.ws.adaptor_streaming import on_connect_invocations
from syntara.core.websocket.close_codes import UNSUPPORTED_DATA


@pytest.fixture
def mock_streaming_service() -> MagicMock:
    """Create a mock streaming service."""
    service = MagicMock()
    service.stream_events_to_websocket = AsyncMock()
    return service


class TestOnConnectInvocations:
    """Test cases for on_connect_invocations WebSocket handler."""

    async def test_invalid_invocation_id_closes_connection(self, mock_websocket: MagicMock) -> None:
        """Test that invalid UUID in path closes connection with error."""
        # Setup: Invalid UUID in path
        mock_websocket.url.path = "/ws/agent_orchestrator/v1/invocations/not-a-uuid"
        mock_websocket.query_params = {}

        # Execute
        await on_connect_invocations(mock_websocket, "test-conn-1")

        # Verify: Connection closed with appropriate error
        mock_websocket.close.assert_called_once_with(code=UNSUPPORTED_DATA, reason="Invalid invocation ID")

    async def test_invalid_replay_count_closes_connection(
        self,
        mock_websocket: MagicMock,
    ) -> None:
        """Test that invalid replay_count closes connection with validation error."""
        # Setup: Valid UUID, invalid replay_count
        invocation_id = uuid4()
        mock_websocket.url.path = f"/ws/agent_orchestrator/v1/invocations/{invocation_id}"
        mock_websocket.query_params = {"replay_count": "invalid"}

        # Execute
        await on_connect_invocations(mock_websocket, "test-conn-1")

        # Verify: Connection closed with validation error
        mock_websocket.close.assert_called_once()
        call_args = mock_websocket.close.call_args
        assert call_args.kwargs["code"] == UNSUPPORTED_DATA
        assert "must be 'all', '0', or a non-negative integer string" in call_args.kwargs["reason"]

    async def test_negative_replay_count_closes_connection(
        self,
        mock_websocket: MagicMock,
    ) -> None:
        """Test that negative replay_count closes connection with validation error."""
        # Setup: Valid UUID, negative replay_count
        invocation_id = uuid4()
        mock_websocket.url.path = f"/ws/agent_orchestrator/v1/invocations/{invocation_id}"
        mock_websocket.query_params = {"replay_count": "-5"}

        # Execute
        await on_connect_invocations(mock_websocket, "test-conn-1")

        # Verify: Connection closed with validation error
        mock_websocket.close.assert_called_once()
        call_args = mock_websocket.close.call_args
        assert call_args.kwargs["code"] == UNSUPPORTED_DATA
        assert "non-negative" in call_args.kwargs["reason"]

    async def test_invalid_last_event_id_format_closes_connection(
        self,
        mock_websocket: MagicMock,
    ) -> None:
        """Test that invalid last_event_id format closes connection with validation error."""
        # Setup: Valid UUID, invalid last_event_id format
        invocation_id = uuid4()
        mock_websocket.url.path = f"/ws/agent_orchestrator/v1/invocations/{invocation_id}"
        mock_websocket.query_params = {"last_event_id": "invalid-format"}

        # Execute
        await on_connect_invocations(mock_websocket, "test-conn-1")

        # Verify: Connection closed with validation error
        mock_websocket.close.assert_called_once()
        call_args = mock_websocket.close.call_args
        assert call_args.kwargs["code"] == UNSUPPORTED_DATA
        assert "timestamp-sequence" in call_args.kwargs["reason"]

    async def test_valid_parameters_calls_streaming_service(
        self,
        mock_websocket: MagicMock,
        mock_streaming_service: MagicMock,
    ) -> None:
        """Test that valid parameters delegate to streaming service."""
        # Setup: Valid UUID and query params
        invocation_id = uuid4()
        mock_websocket.url.path = f"/ws/agent_orchestrator/v1/invocations/{invocation_id}"
        mock_websocket.query_params = {"replay_count": "25", "last_event_id": "1234567890-5"}
        mock_websocket.app.state.streaming_service = mock_streaming_service

        # Execute
        await on_connect_invocations(mock_websocket, "test-conn-1")

        # Verify: Streaming service called with validated parameters
        mock_streaming_service.stream_events_to_websocket.assert_called_once_with(
            websocket=mock_websocket,
            invocation_id=invocation_id,
            replay_count="25",
            last_event_id="1234567890-5",
            connection_id="test-conn-1",
        )
        # Connection should NOT be closed for valid params
        mock_websocket.close.assert_not_called()

    async def test_default_query_parameters(
        self,
        mock_websocket: MagicMock,
        mock_streaming_service: MagicMock,
    ) -> None:
        """Test that missing query parameters use defaults."""
        # Setup: Valid UUID, no query params
        invocation_id = uuid4()
        mock_websocket.url.path = f"/ws/agent_orchestrator/v1/invocations/{invocation_id}"
        mock_websocket.query_params = {}  # Empty query params
        mock_websocket.app.state.streaming_service = mock_streaming_service

        # Execute
        await on_connect_invocations(mock_websocket, "test-conn-1")

        # Verify: Defaults used
        mock_streaming_service.stream_events_to_websocket.assert_called_once_with(
            websocket=mock_websocket,
            invocation_id=invocation_id,
            replay_count="10",  # Default
            last_event_id=None,  # Default
            connection_id="test-conn-1",
        )

    async def test_special_replay_count_all(
        self,
        mock_websocket: MagicMock,
        mock_streaming_service: MagicMock,
    ) -> None:
        """Test that replay_count='all' is accepted."""
        # Setup: Valid UUID, replay_count='all'
        invocation_id = uuid4()
        mock_websocket.url.path = f"/ws/agent_orchestrator/v1/invocations/{invocation_id}"
        mock_websocket.query_params = {"replay_count": "all"}
        mock_websocket.app.state.streaming_service = mock_streaming_service

        # Execute
        await on_connect_invocations(mock_websocket, "test-conn-1")

        # Verify: 'all' passed through
        mock_streaming_service.stream_events_to_websocket.assert_called_once()
        call_args = mock_streaming_service.stream_events_to_websocket.call_args
        assert call_args.kwargs["replay_count"] == "all"

    async def test_special_last_event_id_zero(
        self,
        mock_websocket: MagicMock,
        mock_streaming_service: MagicMock,
    ) -> None:
        """Test that last_event_id='0' is accepted."""
        # Setup: Valid UUID, last_event_id='0'
        invocation_id = uuid4()
        mock_websocket.url.path = f"/ws/agent_orchestrator/v1/invocations/{invocation_id}"
        mock_websocket.query_params = {"last_event_id": "0"}
        mock_websocket.app.state.streaming_service = mock_streaming_service

        # Execute
        await on_connect_invocations(mock_websocket, "test-conn-1")

        # Verify: '0' passed through
        mock_streaming_service.stream_events_to_websocket.assert_called_once()
        call_args = mock_streaming_service.stream_events_to_websocket.call_args
        assert call_args.kwargs["last_event_id"] == "0"

    async def test_special_last_event_id_dollar(
        self,
        mock_websocket: MagicMock,
        mock_streaming_service: MagicMock,
    ) -> None:
        """Test that last_event_id='$' is accepted."""
        # Setup: Valid UUID, last_event_id='$'
        invocation_id = uuid4()
        mock_websocket.url.path = f"/ws/agent_orchestrator/v1/invocations/{invocation_id}"
        mock_websocket.query_params = {"last_event_id": "$"}
        mock_websocket.app.state.streaming_service = mock_streaming_service

        # Execute
        await on_connect_invocations(mock_websocket, "test-conn-1")

        # Verify: '$' passed through
        mock_streaming_service.stream_events_to_websocket.assert_called_once()
        call_args = mock_streaming_service.stream_events_to_websocket.call_args
        assert call_args.kwargs["last_event_id"] == "$"

    async def test_valid_timestamp_sequence_format(
        self,
        mock_websocket: MagicMock,
        mock_streaming_service: MagicMock,
    ) -> None:
        """Test that valid timestamp-sequence format is accepted."""
        # Setup: Valid Redis stream ID format
        invocation_id = uuid4()
        mock_websocket.url.path = f"/ws/agent_orchestrator/v1/invocations/{invocation_id}"
        mock_websocket.query_params = {"last_event_id": "1691431234567-42"}
        mock_websocket.app.state.streaming_service = mock_streaming_service

        # Execute
        await on_connect_invocations(mock_websocket, "test-conn-1")

        # Verify: Valid format passed through
        mock_streaming_service.stream_events_to_websocket.assert_called_once()
        call_args = mock_streaming_service.stream_events_to_websocket.call_args
        assert call_args.kwargs["last_event_id"] == "1691431234567-42"

    async def test_extra_query_params_ignored(
        self,
        mock_websocket: MagicMock,
        mock_streaming_service: MagicMock,
    ) -> None:
        """Test that extra query parameters are ignored (no error)."""
        # Setup: Valid params plus extra unknown param
        invocation_id = uuid4()
        mock_websocket.url.path = f"/ws/agent_orchestrator/v1/invocations/{invocation_id}"
        mock_websocket.query_params = {"replay_count": "10", "unknown_param": "should_be_ignored"}
        mock_websocket.app.state.streaming_service = mock_streaming_service

        # Execute
        await on_connect_invocations(mock_websocket, "test-conn-1")

        # Verify: No error, streaming proceeds normally
        mock_streaming_service.stream_events_to_websocket.assert_called_once()
        mock_websocket.close.assert_not_called()
