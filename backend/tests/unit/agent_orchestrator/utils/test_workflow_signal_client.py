"""Unit tests for WorkflowSignalClient."""

from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest
import respx

from syntara.agent_orchestrator.utils.workflow_signal_client import WorkflowSignalClient, validate_signal_url

_BASE_URL = "https://nexus:8000/api/v1"
_EXEC_UUID = "12345678-1234-5678-1234-567812345678"
_SIGNAL_URL = f"{_BASE_URL}/executions/{_EXEC_UUID}/activities/step_1/signal"


class TestValidateSignalUrl:
    """Tests for validate_signal_url path structure validation."""

    def test_valid_signal_url_accepted(self) -> None:
        validate_signal_url(_SIGNAL_URL)

    def test_valid_url_with_hyphenated_activity_id(self) -> None:
        url = f"{_BASE_URL}/executions/{_EXEC_UUID}/activities/my-step.v2/signal"
        validate_signal_url(url)

    def test_valid_url_with_different_host(self) -> None:
        url = f"https://other-host:8000/api/v1/executions/{_EXEC_UUID}/activities/step_1/signal"
        validate_signal_url(url)

    def test_valid_url_with_http_scheme(self) -> None:
        url = f"http://nexus:8000/api/v1/executions/{_EXEC_UUID}/activities/step_1/signal"
        validate_signal_url(url)

    def test_rejects_invalid_scheme(self) -> None:
        url = f"ftp://nexus:8000/api/v1/executions/{_EXEC_UUID}/activities/step_1/signal"
        with pytest.raises(ValueError, match="http or https"):
            validate_signal_url(url)

    def test_rejects_arbitrary_path(self) -> None:
        url = "https://nexus:8000/api/v1/workflows/some-id/versions/1/publish"
        with pytest.raises(ValueError, match="not a valid signal endpoint"):
            validate_signal_url(url)

    def test_rejects_invalid_execution_id(self) -> None:
        url = f"{_BASE_URL}/executions/not-a-uuid/activities/step_1/signal"
        with pytest.raises(ValueError, match="not a valid signal endpoint"):
            validate_signal_url(url)

    def test_rejects_loopback_ssrf_without_signal_path(self) -> None:
        url = "https://127.0.0.1:9911/some/path"
        with pytest.raises(ValueError, match="not a valid signal endpoint"):
            validate_signal_url(url)

    def test_rejects_extra_path_segments(self) -> None:
        url = f"{_BASE_URL}/executions/{_EXEC_UUID}/activities/step_1/signal/extra"
        with pytest.raises(ValueError, match="not a valid signal endpoint"):
            validate_signal_url(url)

    def test_rejects_publish_endpoint_ssrf(self) -> None:
        """The exact exploit from the bug report: redirect to publish endpoint."""
        url = "https://nexus:8000/api/v1/workflows/victim-wf-id/versions/1/publish"
        with pytest.raises(ValueError, match="not a valid signal endpoint"):
            validate_signal_url(url)

    def test_rejects_query_string(self) -> None:
        url = f"{_SIGNAL_URL}?override=true"
        with pytest.raises(ValueError, match="query string or fragment"):
            validate_signal_url(url)

    def test_rejects_fragment(self) -> None:
        url = f"{_SIGNAL_URL}#section"
        with pytest.raises(ValueError, match="query string or fragment"):
            validate_signal_url(url)


class TestWorkflowSignalClientSendSuccessSignal:
    """Tests for WorkflowSignalClient.send_success_signal."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_success_signal_with_full_result(self) -> None:
        """Test sending success signal with complete result data."""
        invocation_id = UUID(_EXEC_UUID)
        result = {
            "content": "Analysis complete",
            "response_metadata": {
                "model": "claude-3-5-sonnet-20241022",
                "source": "streaming",
            },
            "used_tools": [{"name": "search", "count": 2}],
        }

        route = respx.post(_SIGNAL_URL).mock(return_value=httpx.Response(200))

        await WorkflowSignalClient.send_success_signal(_SIGNAL_URL, invocation_id, result)

        assert route.called
        assert route.call_count == 1

        request = route.calls[0].request
        payload = request.content.decode("utf-8")
        assert _EXEC_UUID in payload
        assert '"status":"completed"' in payload
        assert '"content":"Analysis complete"' in payload
        assert '"used_tools"' in payload
        assert '"search"' in payload
        assert "GenericAgent" in payload

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_success_signal_omits_raw_tool_calls(self) -> None:
        """Raw tool_calls (may include args/secrets) must not be forwarded on the signal."""
        invocation_id = UUID(_EXEC_UUID)
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

        route = respx.post(_SIGNAL_URL).mock(return_value=httpx.Response(200))

        await WorkflowSignalClient.send_success_signal(_SIGNAL_URL, invocation_id, result)

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
        invocation_id = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
        result = {"content": "Done"}

        route = respx.post(_SIGNAL_URL).mock(return_value=httpx.Response(200))

        await WorkflowSignalClient.send_success_signal(_SIGNAL_URL, invocation_id, result)

        assert route.called
        request = route.calls[0].request
        payload = request.content.decode("utf-8")
        assert '"content":"Done"' in payload

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_success_signal_raises_on_http_error(self) -> None:
        """Test that send_success_signal raises on HTTP error."""
        invocation_id = UUID(_EXEC_UUID)
        result = {"content": "Test"}

        respx.post(_SIGNAL_URL).mock(return_value=httpx.Response(500, text="Internal Server Error"))

        with pytest.raises(httpx.HTTPStatusError):
            await WorkflowSignalClient.send_success_signal(_SIGNAL_URL, invocation_id, result)

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_success_signal_raises_on_connection_error(self) -> None:
        """Test that send_success_signal raises on connection error."""
        invocation_id = UUID(_EXEC_UUID)
        result = {"content": "Test"}

        respx.post(_SIGNAL_URL).mock(side_effect=httpx.ConnectError("Connection failed"))

        with pytest.raises(httpx.ConnectError):
            await WorkflowSignalClient.send_success_signal(_SIGNAL_URL, invocation_id, result)

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_success_signal_includes_timestamp(self) -> None:
        """Test that success signal includes ISO timestamp."""
        invocation_id = UUID(_EXEC_UUID)
        result = {"content": "Test"}

        route = respx.post(_SIGNAL_URL).mock(return_value=httpx.Response(200))

        before_time = datetime.now(UTC)
        await WorkflowSignalClient.send_success_signal(_SIGNAL_URL, invocation_id, result)
        after_time = datetime.now(UTC)

        request = route.calls[0].request
        payload = request.content.decode("utf-8")
        assert '"timestamp":' in payload

        import json

        data = json.loads(payload)
        timestamp_str = data["signal_data"]["timestamp"]
        timestamp = datetime.fromisoformat(timestamp_str)
        assert before_time <= timestamp <= after_time

    @pytest.mark.asyncio
    async def test_send_success_signal_rejects_invalid_url(self) -> None:
        """Success signal must raise on SSRF attempt, not silently proceed."""
        invocation_id = UUID(_EXEC_UUID)
        result = {"content": "Test"}

        with pytest.raises(ValueError, match="not a valid signal endpoint"):
            await WorkflowSignalClient.send_success_signal("https://evil.com/steal", invocation_id, result)


class TestWorkflowSignalClientSendFailureSignal:
    """Tests for WorkflowSignalClient.send_failure_signal."""

    @pytest.mark.asyncio
    async def test_send_failure_signal_skips_when_no_callback_url(self) -> None:
        """Test that send_failure_signal skips sending when callback_url is None."""
        callback_url = None
        invocation_id = UUID(_EXEC_UUID)
        error = ValueError("Test error")

        await WorkflowSignalClient.send_failure_signal(callback_url, invocation_id, error)

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_failure_signal_with_exception(self) -> None:
        """Test sending failure signal with exception details."""
        invocation_id = UUID(_EXEC_UUID)
        error = ValueError("Invalid input parameter")

        route = respx.post(_SIGNAL_URL).mock(return_value=httpx.Response(200))

        await WorkflowSignalClient.send_failure_signal(_SIGNAL_URL, invocation_id, error)

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
        invocation_id = UUID(_EXEC_UUID)
        error = RuntimeError("Something went wrong")

        respx.post(_SIGNAL_URL).mock(return_value=httpx.Response(500))

        await WorkflowSignalClient.send_failure_signal(_SIGNAL_URL, invocation_id, error)

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_failure_signal_swallows_connection_error(self) -> None:
        """Test that send_failure_signal swallows connection errors (best-effort)."""
        invocation_id = UUID(_EXEC_UUID)
        error = Exception("Test error")

        respx.post(_SIGNAL_URL).mock(side_effect=httpx.ConnectError("Connection failed"))

        await WorkflowSignalClient.send_failure_signal(_SIGNAL_URL, invocation_id, error)

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_failure_signal_swallows_timeout(self) -> None:
        """Test that send_failure_signal swallows timeout errors (best-effort)."""
        invocation_id = UUID(_EXEC_UUID)
        error = TimeoutError("Request timed out")

        respx.post(_SIGNAL_URL).mock(side_effect=httpx.TimeoutException("Timeout"))

        await WorkflowSignalClient.send_failure_signal(_SIGNAL_URL, invocation_id, error)

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_failure_signal_includes_timestamp(self) -> None:
        """Test that failure signal includes ISO timestamp."""
        invocation_id = UUID(_EXEC_UUID)
        error = KeyError("missing_key")

        route = respx.post(_SIGNAL_URL).mock(return_value=httpx.Response(200))

        before_time = datetime.now(UTC)
        await WorkflowSignalClient.send_failure_signal(_SIGNAL_URL, invocation_id, error)
        after_time = datetime.now(UTC)

        request = route.calls[0].request
        payload = request.content.decode("utf-8")
        assert '"timestamp":' in payload

        import json

        data = json.loads(payload)
        timestamp_str = data["signal_data"]["timestamp"]
        timestamp = datetime.fromisoformat(timestamp_str)
        assert before_time <= timestamp <= after_time

    @pytest.mark.asyncio
    @respx.mock
    async def test_send_failure_signal_with_custom_exception(self) -> None:
        """Test sending failure signal with custom exception type."""
        invocation_id = UUID(_EXEC_UUID)

        class CustomError(Exception):
            """Custom error for testing."""

        error = CustomError("Custom error message")

        route = respx.post(_SIGNAL_URL).mock(return_value=httpx.Response(200))

        await WorkflowSignalClient.send_failure_signal(_SIGNAL_URL, invocation_id, error)

        request = route.calls[0].request
        payload = request.content.decode("utf-8")
        assert '"error_type":"CustomError"' in payload
        assert '"message":"Custom error message"' in payload

    @pytest.mark.asyncio
    async def test_send_failure_signal_raises_on_invalid_url(self) -> None:
        """Failure signal must NOT swallow SSRF validation errors."""
        invocation_id = UUID(_EXEC_UUID)
        error = RuntimeError("some error")

        with pytest.raises(ValueError, match="not a valid signal endpoint"):
            await WorkflowSignalClient.send_failure_signal("https://evil.com/steal", invocation_id, error)
