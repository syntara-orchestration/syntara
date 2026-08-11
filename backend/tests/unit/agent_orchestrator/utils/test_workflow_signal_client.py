"""Unit tests for WorkflowSignalClient."""

from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
import respx

from syntara.agent_orchestrator.utils.workflow_signal_client import WorkflowSignalClient


class TestWorkflowSignalClientSendSuccessSignal:
    """Tests for WorkflowSignalClient.send_success_signal."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_success_signal_with_full_result(self) -> None:
        """Test sending success signal with complete result data."""
        # Arrange
        callback_url = "https://test-workflow:7233/signal/activity/test-123"
        invocation_id = UUID("12345678-1234-5678-1234-567812345678")
        result = {
            "content": "Analysis complete",
            "response_metadata": {
                "model": "claude-3-5-sonnet-20241022",
                "source": "streaming",
            },
            "used_tools": [{"name": "search", "count": 2}],
        }

        # Mock the HTTP POST
        route = respx.post(callback_url).mock(return_value=httpx.Response(200))

        # Act
        await WorkflowSignalClient.send_success_signal(callback_url, invocation_id, result)

        # Assert
        assert route.called
        assert route.call_count == 1

        # Verify the request payload
        request = route.calls[0].request
        payload = request.content.decode("utf-8")
        assert "12345678-1234-5678-1234-567812345678" in payload
        assert '"status":"completed"' in payload
        assert '"content":"Analysis complete"' in payload
        assert '"used_tools"' in payload
        assert '"search"' in payload
        assert "GenericAgent" in payload

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_success_signal_omits_raw_tool_calls(self) -> None:
        """Raw tool_calls (may include args/secrets) must not be forwarded on the signal."""
        callback_url = "https://workflow/signal"
        invocation_id = UUID("12345678-1234-5678-1234-567812345678")
        result = {
            "content": "done",
            "used_tools": [{"name": "search", "count": 1}],
            "tool_calls": [
                {
                    "name": "search",
                    "args": {"api_key": "secret-token", "query": "users"},
                    "id": "call_1",
                }
            ],
        }

        route = respx.post(callback_url).mock(return_value=httpx.Response(200))

        await WorkflowSignalClient.send_success_signal(callback_url, invocation_id, result)

        import json

        payload = json.loads(route.calls[0].request.content.decode("utf-8"))
        signal_result = payload["signal_data"]["result"]
        assert "tool_calls" not in signal_result
        assert "secret-token" not in route.calls[0].request.content.decode("utf-8")
        assert signal_result["used_tools"] == [{"name": "search", "count": 1}]

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_success_signal_with_minimal_result(self) -> None:
        """Test sending success signal with minimal result data."""
        # Arrange
        callback_url = "https://workflow/signal"
        invocation_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        result = {"content": "Done"}

        # Mock the HTTP POST
        route = respx.post(callback_url).mock(return_value=httpx.Response(200))

        # Act
        await WorkflowSignalClient.send_success_signal(callback_url, invocation_id, result)

        # Assert
        assert route.called
        request = route.calls[0].request
        payload = request.content.decode("utf-8")
        assert '"content":"Done"' in payload

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_success_signal_raises_on_http_error(self) -> None:
        """Test that send_success_signal raises on HTTP error."""
        # Arrange
        callback_url = "https://workflow/signal"
        invocation_id = UUID("12345678-1234-5678-1234-567812345678")
        result = {"content": "Test"}

        # Mock HTTP POST to return 500 error
        respx.post(callback_url).mock(return_value=httpx.Response(500, text="Internal Server Error"))

        # Act & Assert
        with pytest.raises(httpx.HTTPStatusError):
            await WorkflowSignalClient.send_success_signal(callback_url, invocation_id, result)

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_success_signal_raises_on_connection_error(self) -> None:
        """Test that send_success_signal raises on connection error."""
        # Arrange
        callback_url = "https://nonexistent-host:9999/signal"
        invocation_id = UUID("12345678-1234-5678-1234-567812345678")
        result = {"content": "Test"}

        # Mock connection error
        respx.post(callback_url).mock(side_effect=httpx.ConnectError("Connection failed"))

        # Act & Assert
        with pytest.raises(httpx.ConnectError):
            await WorkflowSignalClient.send_success_signal(callback_url, invocation_id, result)

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_success_signal_includes_timestamp(self) -> None:
        """Test that success signal includes ISO timestamp."""
        # Arrange
        callback_url = "https://workflow/signal"
        invocation_id = UUID("12345678-1234-5678-1234-567812345678")
        result = {"content": "Test"}

        # Mock the HTTP POST
        route = respx.post(callback_url).mock(return_value=httpx.Response(200))

        # Act
        before_time = datetime.now(UTC)
        await WorkflowSignalClient.send_success_signal(callback_url, invocation_id, result)
        after_time = datetime.now(UTC)

        # Assert
        request = route.calls[0].request
        payload = request.content.decode("utf-8")
        assert '"timestamp":' in payload

        # Verify timestamp format is ISO 8601
        # The timestamp should be between before_time and after_time
        import json

        data = json.loads(payload)
        timestamp_str = data["signal_data"]["timestamp"]
        timestamp = datetime.fromisoformat(timestamp_str)
        assert before_time <= timestamp <= after_time


class TestWorkflowSignalClientSendFailureSignal:
    """Tests for WorkflowSignalClient.send_failure_signal."""

    @pytest.mark.asyncio
    async def test_send_failure_signal_skips_when_no_callback_url(self) -> None:
        """Test that send_failure_signal skips sending when callback_url is None."""
        # Arrange
        callback_url = None
        invocation_id = UUID("12345678-1234-5678-1234-567812345678")
        error = ValueError("Test error")

        # Act (should not raise, should silently skip)
        await WorkflowSignalClient.send_failure_signal(callback_url, invocation_id, error)

        # Assert - no assertion needed, just verify no exception raised

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_failure_signal_with_exception(self) -> None:
        """Test sending failure signal with exception details."""
        # Arrange
        callback_url = "https://workflow/signal"
        invocation_id = UUID("12345678-1234-5678-1234-567812345678")
        error = ValueError("Invalid input parameter")

        # Mock the HTTP POST
        route = respx.post(callback_url).mock(return_value=httpx.Response(200))

        # Act
        await WorkflowSignalClient.send_failure_signal(callback_url, invocation_id, error)

        # Assert
        assert route.called
        request = route.calls[0].request
        payload = request.content.decode("utf-8")
        assert '"status":"failed"' in payload
        assert '"message":"Invalid input parameter"' in payload
        assert '"error_type":"ValueError"' in payload
        assert "GenericAgent" in payload

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_failure_signal_swallows_http_error(self) -> None:
        """Test that send_failure_signal swallows HTTP errors (best-effort)."""
        # Arrange
        callback_url = "https://workflow/signal"
        invocation_id = UUID("12345678-1234-5678-1234-567812345678")
        error = RuntimeError("Something went wrong")

        # Mock HTTP POST to return 500 error
        respx.post(callback_url).mock(return_value=httpx.Response(500))

        # Act (should not raise despite HTTP error)
        await WorkflowSignalClient.send_failure_signal(callback_url, invocation_id, error)

        # Assert - no exception should be raised (best-effort delivery)

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_failure_signal_swallows_connection_error(self) -> None:
        """Test that send_failure_signal swallows connection errors (best-effort)."""
        # Arrange
        callback_url = "https://nonexistent:9999/signal"
        invocation_id = UUID("12345678-1234-5678-1234-567812345678")
        error = Exception("Test error")

        # Mock connection error
        respx.post(callback_url).mock(side_effect=httpx.ConnectError("Connection failed"))

        # Act (should not raise despite connection error)
        await WorkflowSignalClient.send_failure_signal(callback_url, invocation_id, error)

        # Assert - no exception should be raised (best-effort delivery)

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_failure_signal_swallows_timeout(self) -> None:
        """Test that send_failure_signal swallows timeout errors (best-effort)."""
        # Arrange
        callback_url = "https://workflow/signal"
        invocation_id = UUID("12345678-1234-5678-1234-567812345678")
        error = TimeoutError("Request timed out")

        # Mock timeout error
        respx.post(callback_url).mock(side_effect=httpx.TimeoutException("Timeout"))

        # Act (should not raise despite timeout)
        await WorkflowSignalClient.send_failure_signal(callback_url, invocation_id, error)

        # Assert - no exception should be raised (best-effort delivery)

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_failure_signal_includes_timestamp(self) -> None:
        """Test that failure signal includes ISO timestamp."""
        # Arrange
        callback_url = "https://workflow/signal"
        invocation_id = UUID("12345678-1234-5678-1234-567812345678")
        error = KeyError("missing_key")

        # Mock the HTTP POST
        route = respx.post(callback_url).mock(return_value=httpx.Response(200))

        # Act
        before_time = datetime.now(UTC)
        await WorkflowSignalClient.send_failure_signal(callback_url, invocation_id, error)
        after_time = datetime.now(UTC)

        # Assert
        request = route.calls[0].request
        payload = request.content.decode("utf-8")
        assert '"timestamp":' in payload

        # Verify timestamp is valid ISO 8601
        import json

        data = json.loads(payload)
        timestamp_str = data["signal_data"]["timestamp"]
        timestamp = datetime.fromisoformat(timestamp_str)
        assert before_time <= timestamp <= after_time

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_failure_signal_with_custom_exception(self) -> None:
        """Test sending failure signal with custom exception type."""
        # Arrange
        callback_url = "https://workflow/signal"
        invocation_id = UUID("12345678-1234-5678-1234-567812345678")

        class CustomError(Exception):
            """Custom error for testing."""

        error = CustomError("Custom error message")

        # Mock the HTTP POST
        route = respx.post(callback_url).mock(return_value=httpx.Response(200))

        # Act
        await WorkflowSignalClient.send_failure_signal(callback_url, invocation_id, error)

        # Assert
        request = route.calls[0].request
        payload = request.content.decode("utf-8")
        assert '"error_type":"CustomError"' in payload
        assert '"message":"Custom error message"' in payload
