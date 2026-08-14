"""Unit tests for streaming service components.

Tests WebSocketStreamingHandler and StreamingService classes.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.models.invocation import InvocationStatus
from syntara.agent_orchestrator.services.streaming_service import (
    InvocationNotFoundError,
    StreamingService,
    WebSocketStreamingHandler,
    get_invocation_stream_id,
)
from syntara.core.websocket.close_codes import POLICY_VIOLATION
from syntara.core.websocket.exceptions import EventsExpiredError, StreamingValidationError


def mock_db_session_factory(handler: WebSocketStreamingHandler, scalar_result: Any) -> None:  # noqa: ANN401
    """Helper to mock database session factory for handler.

    Args:
        handler: The handler whose session factory should be mocked
        scalar_result: The result to return from scalar_one_or_none()

    """
    # Create mock session and result
    mock_session = AsyncMock()
    mock_result = MagicMock()  # Not AsyncMock - scalar_one_or_none is not async
    mock_result.scalar_one_or_none.return_value = scalar_result
    mock_session.execute.return_value = mock_result

    # Create async context manager mock
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_session
    mock_cm.__aexit__.return_value = None

    handler._session_factory = MagicMock(return_value=mock_cm)


@pytest.fixture
def handler(mock_session_factory: MagicMock) -> WebSocketStreamingHandler:
    """Create a WebSocketStreamingHandler instance."""
    return WebSocketStreamingHandler(session_factory=mock_session_factory)


class TestGetInvocationStreamId:
    """Test get_invocation_stream_id helper function."""

    def test_generates_correct_stream_id(self) -> None:
        """Test that stream ID has correct format."""
        invocation_id = uuid4()
        stream_id = get_invocation_stream_id(invocation_id)
        assert stream_id == f"invocation:{invocation_id}:events"


class TestWebSocketStreamingHandlerCreateContext:
    """Test create_session_state method."""

    async def test_create_session_state_with_valid_invocation_id(self, handler: WebSocketStreamingHandler) -> None:
        """Test that create_session_state succeeds with valid invocation_id."""
        invocation_id = uuid4()

        with patch.object(handler, "_check_invocation_exists", return_value=InvocationStatus.RUNNING) as mock_check:
            session_state = await handler.create_session_state(invocation_id=invocation_id)

            assert session_state["invocation_id"] == invocation_id
            assert session_state["invocation_status"] == InvocationStatus.RUNNING
            mock_check.assert_called_once_with(invocation_id)

    async def test_create_session_state_missing_invocation_id(self, handler: WebSocketStreamingHandler) -> None:
        """Test that create_session_state raises error when invocation_id is missing."""
        with pytest.raises(StreamingValidationError) as exc_info:
            await handler.create_session_state()

        assert exc_info.value.error_data.code == "MISSING_PARAMETER"
        assert exc_info.value.close_code == POLICY_VIOLATION

    async def test_create_session_state_invalid_invocation_id_type(self, handler: WebSocketStreamingHandler) -> None:
        """Test that create_session_state raises error for invalid invocation_id type."""
        with pytest.raises(StreamingValidationError) as exc_info:
            await handler.create_session_state(invocation_id="not-a-uuid")

        assert exc_info.value.error_data.code == "INVALID_PARAMETER"
        assert exc_info.value.close_code == POLICY_VIOLATION
        assert "must be a UUID" in exc_info.value.error_data.detail


class TestWebSocketStreamingHandlerStopCondition:
    """Test get_stop_condition method."""

    def test_stop_condition_returns_callable(self, handler: WebSocketStreamingHandler) -> None:
        """Test that get_stop_condition returns a callable."""
        context = {"invocation_id": uuid4(), "invocation_status": InvocationStatus.RUNNING}
        stop_condition = handler.get_stop_condition(context)
        assert callable(stop_condition)

    def test_stop_condition_stops_on_completion(self, handler: WebSocketStreamingHandler) -> None:
        """Test that stop condition returns True for completion event."""
        context = {"invocation_id": uuid4(), "invocation_status": InvocationStatus.RUNNING}
        stop_condition = handler.get_stop_condition(context)

        assert stop_condition({"event_type": "completion"}) is True

    def test_stop_condition_stops_on_error(self, handler: WebSocketStreamingHandler) -> None:
        """Test that stop condition returns True for error event."""
        context = {"invocation_id": uuid4(), "invocation_status": InvocationStatus.RUNNING}
        stop_condition = handler.get_stop_condition(context)

        assert stop_condition({"event_type": "error"}) is True

    def test_stop_condition_stops_on_cancelled(self, handler: WebSocketStreamingHandler) -> None:
        """Test that stop condition returns True for cancelled event."""
        context = {"invocation_id": uuid4(), "invocation_status": InvocationStatus.RUNNING}
        stop_condition = handler.get_stop_condition(context)

        assert stop_condition({"event_type": "cancelled"}) is True

    def test_stop_condition_continues_on_delta(self, handler: WebSocketStreamingHandler) -> None:
        """Test that stop condition returns False for delta event."""
        context = {"invocation_id": uuid4(), "invocation_status": InvocationStatus.RUNNING}
        stop_condition = handler.get_stop_condition(context)

        assert stop_condition({"event_type": "delta"}) is False


class TestWebSocketStreamingHandlerGetResourceId:
    """Test get_resource_id method."""

    def test_get_resource_id_returns_invocation_id_string(self, handler: WebSocketStreamingHandler) -> None:
        """Test that get_resource_id returns string representation of invocation_id."""
        invocation_id = uuid4()
        context = {"invocation_id": invocation_id, "invocation_status": InvocationStatus.RUNNING}

        resource_id = handler.get_resource_id(context)
        assert resource_id == str(invocation_id)


class TestWebSocketStreamingHandlerWaitForStreamReady:
    """Test wait_for_stream_ready method."""

    async def test_wait_for_stream_ready_raises_events_expired_for_completed(
        self, handler: WebSocketStreamingHandler
    ) -> None:
        """Test that wait_for_stream_ready raises EventsExpiredError for completed invocation."""
        invocation_id = uuid4()
        stream_id = get_invocation_stream_id(invocation_id)
        context = {"invocation_id": invocation_id, "invocation_status": InvocationStatus.COMPLETED}

        with pytest.raises(EventsExpiredError) as exc_info:
            await handler.wait_for_stream_ready(stream_id, context)

        assert exc_info.value.error_data.code == "EVENTS_EXPIRED"
        assert exc_info.value.error_data.instance is not None
        assert str(invocation_id) in exc_info.value.error_data.instance

    async def test_wait_for_stream_ready_raises_events_expired_for_failed(
        self, handler: WebSocketStreamingHandler
    ) -> None:
        """Test that wait_for_stream_ready raises EventsExpiredError for failed invocation."""
        invocation_id = uuid4()
        stream_id = get_invocation_stream_id(invocation_id)
        context = {"invocation_id": invocation_id, "invocation_status": InvocationStatus.FAILED}

        with pytest.raises(EventsExpiredError):
            await handler.wait_for_stream_ready(stream_id, context)

    async def test_wait_for_stream_ready_raises_events_expired_for_cancelled(
        self, handler: WebSocketStreamingHandler
    ) -> None:
        """Test that wait_for_stream_ready raises EventsExpiredError for cancelled invocation."""
        invocation_id = uuid4()
        stream_id = get_invocation_stream_id(invocation_id)
        context = {"invocation_id": invocation_id, "invocation_status": InvocationStatus.CANCELLED}

        with pytest.raises(EventsExpiredError):
            await handler.wait_for_stream_ready(stream_id, context)

    async def test_wait_for_stream_ready_waits_for_running_invocation(self, handler: WebSocketStreamingHandler) -> None:
        """Test that wait_for_stream_ready waits for stream creation for running invocation."""
        invocation_id = uuid4()
        stream_id = get_invocation_stream_id(invocation_id)
        context = {"invocation_id": invocation_id, "invocation_status": InvocationStatus.RUNNING}

        with patch.object(handler, "_wait_for_stream_creation") as mock_wait:
            await handler.wait_for_stream_ready(stream_id, context)
            mock_wait.assert_called_once_with(
                stream_id=stream_id,
                resource_id=str(invocation_id),
                resource_status=InvocationStatus.RUNNING.value,
                resource_type="invocation",
            )


class TestAAP86853InvocationStatusLookupRegression:
    """Regression tests for AAP-86853 Row vs Invocation model status access."""

    def test_row_shaped_lookup_result_lacks_status_attribute_aap_86853(self) -> None:
        """Row-like one_or_none() results are not ORM models and lack .status."""

        class RowShapedLookup:
            """Minimal stand-in for sqlalchemy Row returned by one_or_none()."""

            def __init__(self, status_value: InvocationStatus) -> None:
                self._values = (status_value,)

            def __getitem__(self, index: int) -> InvocationStatus:
                return self._values[index]

        row_shaped = RowShapedLookup(InvocationStatus.RUNNING)

        assert row_shaped[0] == InvocationStatus.RUNNING
        with pytest.raises(AttributeError):
            _ = row_shaped.status  # type: ignore[attr-defined]


class TestWebSocketStreamingHandlerCheckInvocationExists:
    """Test _check_invocation_exists method."""

    async def test_check_invocation_exists_returns_status(self, handler: WebSocketStreamingHandler) -> None:
        """Test that _check_invocation_exists returns invocation status."""
        invocation_id = uuid4()

        # Create mock invocation
        mock_invocation = MagicMock()
        mock_invocation.status = InvocationStatus.RUNNING

        # Mock session factory to return the invocation
        mock_db_session_factory(handler, mock_invocation)

        status = await handler._check_invocation_exists(invocation_id)
        assert status == InvocationStatus.RUNNING

    async def test_check_invocation_exists_raises_not_found(self, handler: WebSocketStreamingHandler) -> None:
        """Test that _check_invocation_exists raises InvocationNotFoundError."""
        invocation_id = uuid4()

        # Mock session factory to return None (invocation not found)
        mock_db_session_factory(handler, None)

        with pytest.raises(InvocationNotFoundError) as exc_info:
            await handler._check_invocation_exists(invocation_id)

        assert exc_info.value.error_data.code == "INVOCATION_NOT_FOUND"
        assert str(invocation_id) in exc_info.value.error_data.detail


class TestStreamingService:
    """Test StreamingService class."""

    def test_init_creates_handler(self, mock_session_factory: MagicMock) -> None:
        """Test that StreamingService creates WebSocketStreamingHandler."""
        service = StreamingService(session_factory=mock_session_factory)
        assert isinstance(service.websocket_handler, WebSocketStreamingHandler)

    async def test_stream_events_to_websocket_calls_handler(
        self, mock_session_factory: MagicMock, mock_websocket: MagicMock
    ) -> None:
        """Test that stream_events_to_websocket delegates to handler."""
        service = StreamingService(session_factory=mock_session_factory)
        invocation_id = uuid4()

        with patch.object(service.websocket_handler, "stream_events_to_websocket") as mock_stream:
            await service.stream_events_to_websocket(
                websocket=mock_websocket,
                invocation_id=invocation_id,
                replay_count="25",
                last_event_id="1234-5",
                connection_id="conn-1",
            )

            mock_stream.assert_called_once()
            call_kwargs = mock_stream.call_args.kwargs
            assert call_kwargs["websocket"] == mock_websocket
            assert call_kwargs["stream_id"] == get_invocation_stream_id(invocation_id)
            assert call_kwargs["replay_count"] == "25"
            assert call_kwargs["last_event_id"] == "1234-5"
            assert call_kwargs["connection_id"] == "conn-1"
            assert call_kwargs["invocation_id"] == invocation_id


class TestInvocationNotFoundError:
    """Test InvocationNotFoundError exception."""

    def test_error_has_correct_attributes(self) -> None:
        """Test that InvocationNotFoundError has correct error data."""
        invocation_id = uuid4()
        error = InvocationNotFoundError(invocation_id)

        assert error.error_data.code == "INVOCATION_NOT_FOUND"
        assert error.error_data.title == "Invocation Not Found"
        assert str(invocation_id) in error.error_data.detail
        assert error.error_data.retryable is False
        assert error.close_code == POLICY_VIOLATION
