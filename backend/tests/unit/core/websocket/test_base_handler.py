"""Unit tests for BaseWebSocketStreamingHandler.

Tests the template method pattern and core streaming logic.
"""

from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.core.models.error import ErrorData
from syntara.core.websocket.base_handler import BaseWebSocketStreamingHandler
from syntara.core.websocket.close_codes import INTERNAL_ERROR, NORMAL_CLOSURE
from syntara.core.websocket.exceptions import StreamingValidationError


class ConcreteHandler(BaseWebSocketStreamingHandler):
    """Concrete implementation for testing."""

    def __init__(self, session_factory: Any | None = None) -> None:  # noqa: ANN401
        """Initialize concrete handler."""
        super().__init__(session_factory=session_factory, channel_name="test")
        self.create_session_state_called = False
        self.get_stop_condition_called = False
        self.get_resource_id_called = False

    async def create_session_state(self, **params: Any) -> dict[str, Any]:  # noqa: ANN401
        """Test implementation of create_session_state."""
        self.create_session_state_called = True
        resource_id = params.get("resource_id")
        if not resource_id:
            error_data = ErrorData(
                type="https://api.example.com/errors/missing-parameter",
                title="Missing Parameter",
                detail="resource_id is required",
                code="MISSING_PARAMETER",
                retryable=False,
                instance="/test",
            )
            raise StreamingValidationError(error_data, INTERNAL_ERROR)
        return {"resource_id": resource_id}

    def get_stop_condition(self, session_state: dict[str, Any]) -> Callable[[dict[str, Any]], bool]:
        """Test implementation of get_stop_condition."""
        self.get_stop_condition_called = True
        return lambda e: e.get("event_type") == "stop"

    def get_resource_id(self, session_state: dict[str, Any]) -> str:
        """Test implementation of get_resource_id."""
        self.get_resource_id_called = True
        return str(session_state["resource_id"])


@pytest.fixture
def handler() -> ConcreteHandler:
    """Create a test handler instance."""
    return ConcreteHandler()


@pytest.fixture
def mock_stream_client_with_no_events() -> MagicMock:
    """Create a mock StreamClient that returns no events."""
    mock_client = AsyncMock()
    mock_client.info.return_value = {"exists": True}

    async def mock_events(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        return
        yield  # NOSONAR - Make this an async generator (yield intentionally unreachable)

    # Use MagicMock for events to avoid AsyncMock wrapping
    mock_client.events = MagicMock(return_value=mock_events())
    return mock_client


@pytest.fixture
def mock_lifecycle_manager() -> MagicMock:
    """Create a mock connection lifecycle manager."""
    mock_mgr = MagicMock()
    mock_mgr.add_connection.return_value = "conn-1"
    mock_mgr.activate_connection = MagicMock()
    mock_mgr.remove_connection = MagicMock()
    return mock_mgr


class TestBaseHandlerTemplatePattern:
    """Test template method pattern implementation."""

    async def test_create_session_state_called_on_stream(
        self,
        handler: ConcreteHandler,
        mock_websocket: MagicMock,
        mock_stream_client_with_no_events: MagicMock,
        mock_lifecycle_manager: MagicMock,
    ) -> None:
        """Test that create_session_state is called during streaming."""
        resource_id = str(uuid4())
        stream_id = f"test:{resource_id}:events"

        with (
            patch("syntara.core.websocket.base_handler.StreamClient") as mock_stream_client,
            patch("syntara.core.websocket.base_handler.get_connection_lifecycle_manager") as mock_lifecycle,
        ):
            mock_stream_client.return_value.__aenter__.return_value = mock_stream_client_with_no_events
            mock_stream_client.return_value.__aexit__.return_value = None
            mock_lifecycle.return_value = mock_lifecycle_manager

            await handler.stream_events_to_websocket(
                websocket=mock_websocket, stream_id=stream_id, resource_id=resource_id
            )

            assert handler.create_session_state_called

    async def test_get_stop_condition_called(
        self,
        handler: ConcreteHandler,
        mock_websocket: MagicMock,
        mock_stream_client_with_no_events: MagicMock,
        mock_lifecycle_manager: MagicMock,
    ) -> None:
        """Test that get_stop_condition is called during streaming."""
        resource_id = str(uuid4())
        stream_id = f"test:{resource_id}:events"

        with (
            patch("syntara.core.websocket.base_handler.StreamClient") as mock_stream_client,
            patch("syntara.core.websocket.base_handler.get_connection_lifecycle_manager") as mock_lifecycle,
        ):
            mock_stream_client.return_value.__aenter__.return_value = mock_stream_client_with_no_events
            mock_stream_client.return_value.__aexit__.return_value = None
            mock_lifecycle.return_value = mock_lifecycle_manager

            await handler.stream_events_to_websocket(
                websocket=mock_websocket, stream_id=stream_id, resource_id=resource_id
            )

            assert handler.get_stop_condition_called

    async def test_get_resource_id_called(
        self,
        handler: ConcreteHandler,
        mock_websocket: MagicMock,
        mock_stream_client_with_no_events: MagicMock,
        mock_lifecycle_manager: MagicMock,
    ) -> None:
        """Test that get_resource_id is called during streaming."""
        resource_id = str(uuid4())
        stream_id = f"test:{resource_id}:events"

        with (
            patch("syntara.core.websocket.base_handler.StreamClient") as mock_stream_client,
            patch("syntara.core.websocket.base_handler.get_connection_lifecycle_manager") as mock_lifecycle,
        ):
            mock_stream_client.return_value.__aenter__.return_value = mock_stream_client_with_no_events
            mock_stream_client.return_value.__aexit__.return_value = None
            mock_lifecycle.return_value = mock_lifecycle_manager

            await handler.stream_events_to_websocket(
                websocket=mock_websocket, stream_id=stream_id, resource_id=resource_id
            )

            assert handler.get_resource_id_called


class TestBaseHandlerErrorHandling:
    """Test error handling in base handler."""

    async def test_validation_error_sends_error_event(
        self, handler: ConcreteHandler, mock_websocket: MagicMock, mock_lifecycle_manager: MagicMock
    ) -> None:
        """Test that validation errors send error event to client."""
        stream_id = "test:missing:events"

        with (
            patch("syntara.core.websocket.base_handler.get_connection_lifecycle_manager") as mock_lifecycle,
        ):
            mock_lifecycle.return_value = mock_lifecycle_manager

            # Missing resource_id will trigger validation error
            with pytest.raises(StreamingValidationError):
                await handler.stream_events_to_websocket(websocket=mock_websocket, stream_id=stream_id)

            # Verify error event sent
            mock_websocket.send_json.assert_called_once()
            error_event = mock_websocket.send_json.call_args[0][0]
            assert error_event["type"] == "error"
            assert error_event["event_type"] == "error"
            assert "resource_id is required" in error_event["data"]["detail"]

    async def test_validation_error_closes_connection(
        self, handler: ConcreteHandler, mock_websocket: MagicMock, mock_lifecycle_manager: MagicMock
    ) -> None:
        """Test that validation errors close WebSocket connection."""
        stream_id = "test:missing:events"

        with (
            patch("syntara.core.websocket.base_handler.get_connection_lifecycle_manager") as mock_lifecycle,
        ):
            mock_lifecycle.return_value = mock_lifecycle_manager

            with pytest.raises(StreamingValidationError):
                await handler.stream_events_to_websocket(websocket=mock_websocket, stream_id=stream_id)

            # Verify connection closed with error code
            mock_websocket.close.assert_called_once()
            assert mock_websocket.close.call_args[1]["code"] == INTERNAL_ERROR

    async def test_unexpected_error_sends_error_event_with_type_field(
        self, mock_websocket: MagicMock, mock_lifecycle_manager: MagicMock
    ) -> None:
        """Test that unexpected errors send error event with type='error' for client switch compatibility."""

        class FailingHandler(ConcreteHandler):
            async def create_session_state(self, **params: Any) -> dict[str, Any]:  # noqa: ANN401
                msg = "Database connection failed"
                raise RuntimeError(msg)

        handler = FailingHandler()
        stream_id = "test:some-id:events"

        with patch("syntara.core.websocket.base_handler.get_connection_lifecycle_manager") as mock_lifecycle:
            mock_lifecycle.return_value = mock_lifecycle_manager

            with pytest.raises(RuntimeError):
                await handler.stream_events_to_websocket(websocket=mock_websocket, stream_id=stream_id)

            mock_websocket.send_json.assert_called_once()
            error_event = mock_websocket.send_json.call_args[0][0]
            assert error_event["type"] == "error"
            assert error_event["event_type"] == "error"
            assert error_event["resource_id"] == "unknown"
            assert error_event["data"]["code"] == "INTERNAL_ERROR"
            assert "Database connection failed" in error_event["data"]["detail"]

    async def test_unexpected_error_truncates_long_detail(
        self, mock_websocket: MagicMock, mock_lifecycle_manager: MagicMock
    ) -> None:
        """Test that long error messages are truncated to fit ErrorData max_length."""

        class FailingHandler(ConcreteHandler):
            async def create_session_state(self, **params: Any) -> dict[str, Any]:  # noqa: ANN401
                raise RuntimeError("x" * 5000)

        handler = FailingHandler()
        stream_id = "test:some-id:events"

        with patch("syntara.core.websocket.base_handler.get_connection_lifecycle_manager") as mock_lifecycle:
            mock_lifecycle.return_value = mock_lifecycle_manager

            with pytest.raises(RuntimeError):
                await handler.stream_events_to_websocket(websocket=mock_websocket, stream_id=stream_id)

            # Error event should still be sent (not dropped due to validation failure)
            mock_websocket.send_json.assert_called_once()
            error_event = mock_websocket.send_json.call_args[0][0]
            assert error_event["type"] == "error"
            assert len(error_event["data"]["detail"]) <= 2000


class TestBaseHandlerStreaming:
    """Test core streaming functionality."""

    async def test_events_sent_to_websocket(
        self, handler: ConcreteHandler, mock_websocket: MagicMock, mock_lifecycle_manager: MagicMock
    ) -> None:
        """Test that events are sent to WebSocket client."""
        resource_id = str(uuid4())
        stream_id = f"test:{resource_id}:events"

        test_events = [
            {"event_type": "data", "data": "event1"},
            {"event_type": "data", "data": "event2"},
            {"event_type": "stop", "data": "done"},
        ]

        with (
            patch("syntara.core.websocket.base_handler.StreamClient") as mock_stream_client,
            patch("syntara.core.websocket.base_handler.get_connection_lifecycle_manager") as mock_lifecycle,
        ):
            # Mock stream client
            mock_client = AsyncMock()
            mock_client.info.return_value = {"exists": True}

            async def mock_events(*args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
                for event in test_events:
                    yield event

            # Use MagicMock for events to avoid AsyncMock wrapping
            mock_client.events = MagicMock(return_value=mock_events())
            mock_stream_client.return_value.__aenter__.return_value = mock_client
            mock_stream_client.return_value.__aexit__.return_value = None

            mock_lifecycle.return_value = mock_lifecycle_manager

            await handler.stream_events_to_websocket(
                websocket=mock_websocket, stream_id=stream_id, resource_id=resource_id
            )

            # Verify all events sent
            assert mock_websocket.send_json.call_count == 3
            sent_events = [call[0][0] for call in mock_websocket.send_json.call_args_list]
            assert sent_events == test_events

    async def test_connection_closed_after_streaming(
        self,
        handler: ConcreteHandler,
        mock_websocket: MagicMock,
        mock_stream_client_with_no_events: MagicMock,
        mock_lifecycle_manager: MagicMock,
    ) -> None:
        """Test that WebSocket connection is closed after streaming completes."""
        resource_id = str(uuid4())
        stream_id = f"test:{resource_id}:events"

        with (
            patch("syntara.core.websocket.base_handler.StreamClient") as mock_stream_client,
            patch("syntara.core.websocket.base_handler.get_connection_lifecycle_manager") as mock_lifecycle,
        ):
            mock_stream_client.return_value.__aenter__.return_value = mock_stream_client_with_no_events
            mock_stream_client.return_value.__aexit__.return_value = None
            mock_lifecycle.return_value = mock_lifecycle_manager

            await handler.stream_events_to_websocket(
                websocket=mock_websocket, stream_id=stream_id, resource_id=resource_id
            )

            # Verify connection closed with normal closure
            mock_websocket.close.assert_called_once()
            assert mock_websocket.close.call_args[1]["code"] == NORMAL_CLOSURE


class TestBaseHandlerReplayParameters:
    """Test replay parameter logic."""

    def test_replay_count_all_returns_start_id_zero(self, handler: ConcreteHandler) -> None:
        """Test that replay_count='all' returns start_id='0-0'."""
        session_state = {"resource_id": "test"}
        start_id, replay = handler.get_replay_parameters("all", None, session_state)
        assert start_id == "0-0"
        assert replay is None

    def test_replay_count_zero_returns_dollar_sign(self, handler: ConcreteHandler) -> None:
        """Test that replay_count='0' returns start_id='$'."""
        session_state = {"resource_id": "test"}
        start_id, replay = handler.get_replay_parameters("0", None, session_state)
        assert start_id == "$"
        assert replay is None

    def test_replay_count_numeric_returns_replay_value(self, handler: ConcreteHandler) -> None:
        """Test that numeric replay_count returns replay parameter."""
        session_state = {"resource_id": "test"}
        start_id, replay = handler.get_replay_parameters("25", None, session_state)
        assert start_id is None
        assert replay == 25

    def test_last_event_id_takes_precedence(self, handler: ConcreteHandler) -> None:
        """Test that last_event_id takes precedence over replay_count."""
        session_state = {"resource_id": "test"}
        start_id, replay = handler.get_replay_parameters("10", "1234567890-5", session_state)
        assert start_id == "1234567890-5"
        assert replay is None

    def test_last_event_id_zero_returns_zero_start_id(self, handler: ConcreteHandler) -> None:
        """Test that last_event_id='0' returns start_id='0-0'."""
        session_state = {"resource_id": "test"}
        start_id, replay = handler.get_replay_parameters("10", "0", session_state)
        assert start_id == "0-0"
        assert replay is None
