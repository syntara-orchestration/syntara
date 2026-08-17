"""Custom exceptions for WebSocket streaming.

Provides base exceptions for WebSocket streaming error handling.
"""

from syntara.core.exceptions import SyntaraError
from syntara.core.models.error import ErrorData
from syntara.core.websocket.close_codes import INTERNAL_ERROR, NORMAL_CLOSURE


class StreamingValidationError(SyntaraError):
    """Base exception for streaming validation errors.

    These exceptions are caught by stream_events_to_websocket() and converted
    to appropriate WebSocket error responses.

    Attributes:
        error_data: RFC 9457 compliant error data
        close_code: WebSocket close code to use when closing the connection

    """

    def __init__(self, error_data: ErrorData, close_code: int) -> None:
        """Initialize streaming validation error.

        Args:
            error_data: RFC 9457 compliant error data
            close_code: WebSocket close code

        """
        self.error_data = error_data
        self.close_code = close_code
        super().__init__(error_data.detail)


class EventsExpiredError(StreamingValidationError):
    """Cache streaming events have expired for a resource."""

    def __init__(self, resource_id: str, resource_status: str, resource_type: str = "resource") -> None:
        """Initialize events expired error.

        Args:
            resource_id: ID of the resource
            resource_status: Current status of the resource
            resource_type: Type of resource (e.g., "invocation", "task", "tool")

        """
        error_data = ErrorData(
            type="https://api.example.com/errors/events-expired",
            title="Streaming Events Expired",
            detail=(
                f"Streaming events have expired. Events are only retained for a limited time. "
                f"Resource status: {resource_status}"
            ),
            code="EVENTS_EXPIRED",
            retryable=False,
            instance=f"/{resource_type}s/{resource_id}",
        )
        super().__init__(error_data, NORMAL_CLOSURE)


class WaitForStreamTimeoutError(StreamingValidationError):
    """Timeout waiting for cache stream creation."""

    def __init__(self, resource_id: str, resource_status: str, resource_type: str = "resource") -> None:
        """Initialize stream timeout error.

        Args:
            resource_id: ID of the resource
            resource_status: Current status of the resource
            resource_type: Type of resource (e.g., "invocation", "task", "tool")

        """
        error_data = ErrorData(
            type="https://api.example.com/errors/timeout-error",
            title="Streaming Timeout",
            detail=f"Timeout waiting for streaming to start. Resource status: {resource_status}",
            code="STREAM_TIMEOUT",
            retryable=True,
            instance=f"/{resource_type}s/{resource_id}",
        )
        super().__init__(error_data, INTERNAL_ERROR)
