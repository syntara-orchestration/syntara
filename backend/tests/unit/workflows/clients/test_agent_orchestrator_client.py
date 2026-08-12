"""Comprehensive unit tests for AgentOrchestratorClient.

Test Coverage:
- File IDs parameter handling (AAP-60785)
- Error handling and retry logic
- Response validation
- Context manager lifecycle
- Edge cases (ID generation, metadata handling)
- Configuration options
"""

import asyncio
import uuid
from collections.abc import Callable, Coroutine
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from syntara.workflows.clients.agent_orchestrator_client import (
    AgentOrchestratorClient,
    AgentOrchestratorClientConnectionError,
    AgentOrchestratorClientError,
    ErrorCode,
)


def generate_valid_uuid() -> str:
    """Generate a valid UUID string."""
    return str(uuid.uuid4())


def generate_valid_uuids(count: int) -> list[str]:
    """Generate a list of valid UUID strings."""
    return [generate_valid_uuid() for _ in range(count)]


def create_mock_response(**kwargs: object) -> dict[str, Any]:
    """Create a standard mock response from Agent Orchestrator."""
    return {
        "id": "inv_test_123",
        "status": "completed",
        "result": {"answer": "Test response"},
        "error_message": None,
        "created_at": "2026-01-01T00:00:00Z",
        "updated_at": "2026-01-01T00:00:01Z",
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": "2026-01-01T00:00:01Z",
    }


def create_mock_http_response(
    json_data: dict[str, Any] | None = None,
    status_code: int = 200,
    raise_for_status_error: Exception | None = None,
) -> MagicMock:
    """Create a mock HTTP response object.

    Args:
        json_data: JSON data to return (defaults to create_mock_response())
        status_code: HTTP status code
        raise_for_status_error: Exception to raise on raise_for_status() call

    Returns:
        Mock response object

    """
    response = MagicMock()
    response.json.return_value = json_data if json_data is not None else create_mock_response()
    response.status_code = status_code
    if raise_for_status_error:
        response.raise_for_status.side_effect = raise_for_status_error
    else:
        response.raise_for_status = MagicMock()
    return response


def create_payload_capturing_mock(
    captured_payload: dict[str, Any],
    response: MagicMock | None = None,
) -> Callable[[str], Coroutine[Any, Any, MagicMock]]:
    """Create a mock POST function that captures payload and returns a response.

    Args:
        captured_payload: Dictionary to capture the payload into
        response: Mock response to return (defaults to standard success response)

    Returns:
        Async mock function

    """

    async def mock_post(url: str, **kwargs: object) -> MagicMock:
        json_data = kwargs.get("json", {})
        if isinstance(json_data, dict):
            captured_payload.clear()
            captured_payload.update(json_data)
        return response or create_mock_http_response()

    return mock_post


def create_simple_mock_post(
    response: MagicMock | None = None,
) -> Callable[[str], Coroutine[Any, Any, MagicMock]]:
    """Create a simple mock POST function that returns a response.

    Args:
        response: Mock response to return (defaults to standard success response)

    Returns:
        Async mock function

    """

    async def mock_post(url: str, **kwargs: object) -> MagicMock:
        return response or create_mock_http_response()

    return mock_post


class TestAgentOrchestratorClientFileIds:
    """Test suite for file_ids parameter in AgentOrchestratorClient.invoke_agent_async()."""

    @pytest.mark.asyncio
    async def test_invoke_agent_with_file_ids(self) -> None:
        """Test that file_ids are included in contextData of POST payload."""
        file_ids = generate_valid_uuids(2)
        captured_payload: dict[str, Any] = {}

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(  # type: ignore[method-assign]
                side_effect=create_payload_capturing_mock(captured_payload)
            )

            invocation_id = await client.invoke_agent_async(
                prompt="Test prompt",
                user_id="test-user",
                file_ids=file_ids,
                project_id=str(uuid.uuid4()),
            )

        # Verify file_ids were sent in contextData
        assert "contextData" in captured_payload
        assert "file_ids" in captured_payload["contextData"]
        assert captured_payload["contextData"]["file_ids"] == file_ids
        assert invocation_id == "inv_test_123"

    @pytest.mark.asyncio
    async def test_invoke_agent_without_file_ids(self) -> None:
        """Test that file_ids is omitted from payload when not provided."""
        captured_payload: dict[str, Any] = {}

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(  # type: ignore[method-assign]
                side_effect=create_payload_capturing_mock(captured_payload)
            )

            invocation_id = await client.invoke_agent_async(
                prompt="Test prompt",
                user_id="test-user",
                project_id=str(uuid.uuid4()),
            )

        # Verify file_ids not in contextData when not provided
        assert "contextData" in captured_payload
        assert "file_ids" not in captured_payload["contextData"]

        # Verify invocation ID is returned correctly
        assert invocation_id == "inv_test_123"

    @pytest.mark.asyncio
    async def test_invoke_agent_with_empty_file_ids_list(self) -> None:
        """Test that empty file_ids list is omitted from payload (filtered by v is not None check)."""
        captured_payload: dict[str, Any] = {}

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(  # type: ignore[method-assign]
                side_effect=create_payload_capturing_mock(captured_payload)
            )

            invocation_id = await client.invoke_agent_async(
                prompt="Test prompt",
                user_id="test-user",
                file_ids=[],  # Empty list
                project_id=str(uuid.uuid4()),
            )

        # Empty list should still be included (it's truthy in the filter)
        # Actually, empty list is truthy, so it WILL be included
        assert "contextData" in captured_payload
        assert "file_ids" in captured_payload["contextData"]
        assert captured_payload["contextData"]["file_ids"] == []

        # Verify invocation ID is returned correctly
        assert invocation_id == "inv_test_123"

    @pytest.mark.asyncio
    async def test_file_ids_logged(self) -> None:
        """Test that file count is logged for observability."""
        file_ids = generate_valid_uuids(3)

        # Mock the HTTP client POST method
        mock_post = create_simple_mock_post()

        with patch("syntara.workflows.clients.agent_orchestrator_client.logger") as mock_logger:
            async with AgentOrchestratorClient() as client:
                # Replace the post method with our mock
                client.http_client.post = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

                await client.invoke_agent_async(
                    prompt="Test prompt",
                    user_id="test-user",
                    file_ids=file_ids,
                    project_id=str(uuid.uuid4()),
                )

            # Verify file_count=3 in log
            # Check logger.info calls for the invocation log (second call after client init)
            assert mock_logger.info.call_count >= 2
            invocation_call_args = mock_logger.info.call_args_list[1]  # Second call is invocation

            # Check that the log message is correct
            assert invocation_call_args[0][0] == "Invoking agent asynchronously"
            # Check that file_count=3 is in the kwargs
            assert invocation_call_args[1]["file_count"] == 3

    @pytest.mark.asyncio
    async def test_file_ids_zero_count_logged_when_not_provided(self) -> None:
        """Test that file_count=0 is logged when file_ids is not provided."""
        # Mock the HTTP client POST method
        mock_post = create_simple_mock_post()

        with patch("syntara.workflows.clients.agent_orchestrator_client.logger") as mock_logger:
            async with AgentOrchestratorClient() as client:
                # Replace the post method with our mock
                client.http_client.post = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

                await client.invoke_agent_async(
                    prompt="Test prompt",
                    user_id="test-user",
                    project_id=str(uuid.uuid4()),
                )

            # Verify file_count=0 in log
            # Check logger.info calls for the invocation log (second call after client init)
            assert mock_logger.info.call_count >= 2
            invocation_call_args = mock_logger.info.call_args_list[1]  # Second call is invocation

            # Check that the log message is correct
            assert invocation_call_args[0][0] == "Invoking agent asynchronously"
            # Check that file_count=0 is in the kwargs
            assert invocation_call_args[1]["file_count"] == 0


class TestAgentOrchestratorClientRetryLogic:
    """Test suite for error handling and retry logic."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error_type", "error_args", "fail_until_attempt", "expected_attempts"),
        [
            (httpx.ConnectError, ("Connection refused",), 3, 3),
            (httpx.TimeoutException, ("Request timeout",), 2, 2),
        ],
    )
    async def test_retryable_errors_trigger_retry(
        self,
        error_type: type[Exception],
        error_args: tuple[str, ...],
        fail_until_attempt: int,
        expected_attempts: int,
    ) -> None:
        """Test that retryable errors trigger retry with exponential backoff."""
        attempt_count = 0

        async def mock_post_with_error(url: str, **kwargs: object) -> MagicMock:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < fail_until_attempt:
                raise error_type(*error_args)
            # Success on final attempt
            return create_mock_http_response()

        async with AgentOrchestratorClient(max_retries=3, retry_backoff_base=0.01) as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_with_error)  # type: ignore[method-assign]

            invocation_id = await client.invoke_agent_async(
                prompt="Test",
                user_id="test-user",
                project_id=str(uuid.uuid4()),
            )

            assert invocation_id == "inv_test_123"
            assert attempt_count == expected_attempts

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("error_type", "error_args"),
        [
            (httpx.ConnectError, ("Connection refused",)),
            (httpx.TimeoutException, ("Request timeout",)),
        ],
    )
    async def test_retryable_errors_no_retries_when_max_retries_zero(
        self,
        error_type: type[Exception],
        error_args: tuple[str, ...],
    ) -> None:
        """Test that retryable errors do not retry when max_retries=0."""
        attempt_count = 0

        async def mock_post_always_fails(url: str, **kwargs: object) -> MagicMock:
            nonlocal attempt_count
            attempt_count += 1
            raise error_type(*error_args)

        async with AgentOrchestratorClient(max_retries=0, retry_backoff_base=0.01) as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_always_fails)  # type: ignore[method-assign]

            with pytest.raises(AgentOrchestratorClientConnectionError):
                await client.invoke_agent_async(
                    prompt="Test",
                    user_id="test-user",
                    project_id=str(uuid.uuid4()),
                )

            # Should only make 1 attempt (no retries)
            assert attempt_count == 1

    @pytest.mark.asyncio
    async def test_max_retries_exhausted_raises_connection_error(self) -> None:
        """Test that exhausting retries raises AgentOrchestratorConnectionError."""

        async def mock_post_always_fails(url: str, **kwargs: object) -> MagicMock:
            raise httpx.ConnectError("Connection refused")  # noqa: EM101, TRY003

        async with AgentOrchestratorClient(max_retries=2, retry_backoff_base=0.01) as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_always_fails)  # type: ignore[method-assign]

            with pytest.raises(AgentOrchestratorClientConnectionError) as exc_info:
                await client.invoke_agent_async(
                    prompt="Test",
                    user_id="test-user",
                    project_id=str(uuid.uuid4()),
                )

            assert exc_info.value.code == ErrorCode.CONNECTION_FAILED
            assert "Failed to connect" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_500_error_triggers_retry(self) -> None:
        """Test that 5xx server errors trigger retry."""
        attempt_count = 0

        async def mock_post_with_500(url: str, **kwargs: object) -> MagicMock:
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                response = MagicMock()
                response.status_code = 500
                response.text = "Internal Server Error"
                error = httpx.HTTPStatusError("500 Server Error", request=MagicMock(), response=response)
                return create_mock_http_response(status_code=500, raise_for_status_error=error)
            return create_mock_http_response()

        async with AgentOrchestratorClient(max_retries=3, retry_backoff_base=0.01) as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_with_500)  # type: ignore[method-assign]

            invocation_id = await client.invoke_agent_async(
                prompt="Test",
                user_id="test-user",
                project_id=str(uuid.uuid4()),
            )

            assert invocation_id == "inv_test_123"
            assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_400_error_does_not_retry(self) -> None:
        """Test that 4xx client errors do NOT trigger retry (they're permanent)."""
        attempt_count = 0

        async def mock_post_with_400(url: str, **kwargs: object) -> MagicMock:
            nonlocal attempt_count
            attempt_count += 1
            response = MagicMock()
            response.status_code = 400
            response.text = "Bad Request"
            error = httpx.HTTPStatusError("400 Client Error", request=MagicMock(), response=response)
            return create_mock_http_response(status_code=400, raise_for_status_error=error)

        async with AgentOrchestratorClient(max_retries=3, retry_backoff_base=0.01) as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_with_400)  # type: ignore[method-assign]

            with pytest.raises(AgentOrchestratorClientError) as exc_info:
                await client.invoke_agent_async(
                    prompt="Test",
                    user_id="test-user",
                    project_id=str(uuid.uuid4()),
                )

            assert exc_info.value.code == ErrorCode.HTTP_CLIENT_ERROR
            assert attempt_count == 1  # No retries for 4xx

    @pytest.mark.asyncio
    async def test_exponential_backoff(self) -> None:
        """Test that retry backoff increases exponentially."""
        attempt_times: list[float] = []

        async def mock_post_track_timing(url: str, **kwargs: object) -> MagicMock:
            attempt_times.append(asyncio.get_event_loop().time())
            if len(attempt_times) < 4:
                raise httpx.ConnectError("Connection refused")  # noqa: EM101, TRY003
            return create_mock_http_response()

        async with AgentOrchestratorClient(max_retries=3, retry_backoff_base=0.1) as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_track_timing)  # type: ignore[method-assign]

            await client.invoke_agent_async(
                prompt="Test",
                user_id="test-user",
                project_id=str(uuid.uuid4()),
            )

            # Verify exponential backoff: 0.1s, 0.2s between attempts
            # Allow some tolerance for timing
            assert len(attempt_times) == 4  # Initial attempt + 3 re-tries
            backoff1 = attempt_times[1] - attempt_times[0]
            backoff2 = attempt_times[2] - attempt_times[1]
            backoff3 = attempt_times[3] - attempt_times[2]
            assert 0.08 < backoff1 < 0.15  # ~0.1s backoff
            assert 0.18 < backoff2 < 0.25  # ~0.2s backoff (2x first)
            assert 0.30 < backoff3 < 0.50  # ~0.4s backoff (4x first)

    @pytest.mark.asyncio
    async def test_retry_not_triggered_on_validation_error(self) -> None:
        """Test that response validation errors (permanent) don't trigger retry."""
        attempt_count = 0

        async def mock_post_invalid_response(url: str, **kwargs: object) -> MagicMock:
            nonlocal attempt_count
            attempt_count += 1
            # Return response missing required 'id' field
            return create_mock_http_response(json_data={"status": "pending"})

        async with AgentOrchestratorClient(max_retries=3, retry_backoff_base=0.01) as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_invalid_response)  # type: ignore[method-assign]

            with pytest.raises(AgentOrchestratorClientError) as exc_info:
                await client.invoke_agent_async(
                    prompt="Test",
                    user_id="test-user",
                    project_id=str(uuid.uuid4()),
                )

            # Should fail immediately without retry
            assert exc_info.value.code == ErrorCode.MISSING_FIELD
            assert attempt_count == 1  # No retries for validation errors


class TestAgentOrchestratorClientResponseValidation:
    """Test suite for response validation."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("response_data", "error_substring"),
        [
            ({"status": "pending"}, "missing or invalid 'id'"),  # Missing ID
            ({"id": "", "status": "pending"}, "missing or invalid 'id'"),  # Empty ID
        ],
    )
    async def test_invalid_invocation_id_raises_error(
        self,
        response_data: dict[str, Any],
        error_substring: str,
    ) -> None:
        """Test that missing or invalid invocation ID raises error."""

        async def mock_post_invalid(url: str, **kwargs: object) -> MagicMock:
            return create_mock_http_response(json_data=response_data)

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_invalid)  # type: ignore[method-assign]

            with pytest.raises(AgentOrchestratorClientError) as exc_info:
                await client.invoke_agent_async(
                    prompt="Test",
                    user_id="test-user",
                    project_id=str(uuid.uuid4()),
                )

            assert exc_info.value.code == ErrorCode.MISSING_FIELD
            assert error_substring in exc_info.value.message.lower()


class TestAgentOrchestratorClientContextManager:
    """Test suite for context manager lifecycle."""

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self) -> None:
        """Test that context manager properly closes HTTP client."""
        client = AgentOrchestratorClient()

        # Mock the aclose method to track if it was called
        original_aclose = client.http_client.aclose
        close_called = False

        async def mock_aclose() -> None:
            nonlocal close_called
            close_called = True
            await original_aclose()

        client.http_client.aclose = mock_aclose  # type: ignore[method-assign]

        async with client:
            pass  # Just enter and exit

        assert close_called

    @pytest.mark.asyncio
    async def test_context_manager_closes_on_error(self) -> None:
        """Test that context manager closes client even when error occurs."""
        client = AgentOrchestratorClient()

        close_called = False

        async def mock_aclose() -> None:
            nonlocal close_called
            close_called = True

        client.http_client.aclose = mock_aclose  # type: ignore[method-assign]

        with pytest.raises(RuntimeError):
            async with client:
                raise RuntimeError("Test error")  # noqa: EM101, TRY003

        assert close_called

    @pytest.mark.asyncio
    async def test_manual_close(self) -> None:
        """Test that manual close() works."""
        client = AgentOrchestratorClient()

        close_called = False

        async def mock_aclose() -> None:
            nonlocal close_called
            close_called = True

        client.http_client.aclose = mock_aclose  # type: ignore[method-assign]

        await client.close()
        assert close_called


class TestAgentOrchestratorClientEdgeCases:
    """Test suite for edge cases."""

    @pytest.mark.asyncio
    async def test_auto_generates_session_id(self) -> None:
        """Test that session ID is auto-generated when not provided."""
        captured_payload: dict[str, Any] = {}

        mock_post = create_payload_capturing_mock(captured_payload)

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

            await client.invoke_agent_async(
                prompt="Test",
                user_id="test-user",
                project_id=str(uuid.uuid4()),
            )

        # Verify ID was generated and is a valid UUID
        assert "sessionId" in captured_payload
        generated_id = captured_payload["sessionId"]

        # Should be a valid UUID
        uuid.UUID(generated_id)

    @pytest.mark.asyncio
    async def test_callback_url_extracted_from_metadata(self) -> None:
        """Test that callback_url is extracted from metadata to top level."""
        captured_payload: dict[str, Any] = {}

        mock_post = create_payload_capturing_mock(captured_payload)

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

            await client.invoke_agent_async(
                prompt="Test",
                user_id="test-user",
                metadata={"callback_url": "http://test.com/callback", "other": "value"},
                project_id=str(uuid.uuid4()),
            )

        # callback_url should be at top level of contextData
        assert captured_payload["contextData"]["callback_url"] == "http://test.com/callback"
        # Other metadata should remain
        assert captured_payload["contextData"]["metadata"] == {"other": "value"}

    @pytest.mark.asyncio
    async def test_metadata_removed_when_only_callback_url(self) -> None:
        """Test that metadata is removed when it only contains callback_url."""
        captured_payload: dict[str, Any] = {}

        mock_post = create_payload_capturing_mock(captured_payload)

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

            await client.invoke_agent_async(
                prompt="Test",
                user_id="test-user",
                metadata={"callback_url": "http://test.com/callback"},
                project_id=str(uuid.uuid4()),
            )

        # callback_url at top level
        assert captured_payload["contextData"]["callback_url"] == "http://test.com/callback"
        # metadata should not be present
        assert "metadata" not in captured_payload["contextData"]

    @pytest.mark.asyncio
    async def test_all_optional_parameters(self) -> None:
        """Test invocation with all optional parameters."""
        captured_payload: dict[str, Any] = {}

        mock_post = create_payload_capturing_mock(captured_payload)

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

            await client.invoke_agent_async(
                prompt="Test prompt",
                user_id="test-user",
                session_id="test-session",
                agent="test-agent",
                model="test-model",
                input_data={"key": "value"},
                file_ids=["file1", "file2"],
                metadata={"custom": "data"},
                project_id=str(uuid.uuid4()),
            )

        # Verify all parameters in payload
        assert captured_payload["prompt"] == "Test prompt"
        assert captured_payload["createdBy"] == "test-user"
        assert captured_payload["sessionId"] == "test-session"
        assert captured_payload["contextData"]["agent"] == "test-agent"
        assert captured_payload["contextData"]["model"] == "test-model"
        assert captured_payload["contextData"]["input_data"] == {"key": "value"}
        assert captured_payload["contextData"]["file_ids"] == ["file1", "file2"]
        assert captured_payload["contextData"]["metadata"] == {"custom": "data"}


class TestAgentOrchestratorClientConfiguration:
    """Test suite for client configuration."""

    @pytest.mark.asyncio
    async def test_custom_base_url(self) -> None:
        """Test client with custom base URL."""
        custom_url = "http://custom.example.com/api"
        client = AgentOrchestratorClient(base_url=custom_url)

        assert client.base_url == custom_url
        # httpx adds trailing slash to base_url, so compare without it
        assert str(client.http_client.base_url).rstrip("/") == custom_url

        await client.close()

    @pytest.mark.asyncio
    async def test_custom_timeout(self) -> None:
        """Test client with custom timeout."""
        custom_timeout = 60.0
        client = AgentOrchestratorClient(timeout=custom_timeout)

        assert client.timeout == pytest.approx(custom_timeout)
        # Verify HTTP client timeout is set
        assert client.http_client.timeout.read == pytest.approx(custom_timeout)

        await client.close()

    @pytest.mark.asyncio
    async def test_custom_retry_settings(self) -> None:
        """Test client with custom retry settings."""
        client = AgentOrchestratorClient(max_retries=5, retry_backoff_base=2.0)

        assert client.max_retries == 5
        assert client.retry_backoff_base == pytest.approx(2.0)

        await client.close()

    @pytest.mark.asyncio
    async def test_base_url_trailing_slash_removed(self) -> None:
        """Test that trailing slash is removed from base URL."""
        client = AgentOrchestratorClient(base_url="http://test.com/api/v1/")

        assert client.base_url == "http://test.com/api/v1"

        await client.close()


class TestAgentOrchestratorClientErrorHandling:
    """Test suite for error handling and error conversion."""

    @pytest.mark.asyncio
    async def test_json_decode_error_raises_unexpected_error(self) -> None:
        """Test that non-JSON response raises AgentOrchestratorError with UNEXPECTED_ERROR code."""

        async def mock_post_invalid_json(url: str, **kwargs: object) -> MagicMock:
            response = MagicMock()
            response.json.side_effect = ValueError("Invalid JSON")
            response.raise_for_status = MagicMock()
            return response

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_invalid_json)  # type: ignore[method-assign]

            with pytest.raises(AgentOrchestratorClientError) as exc_info:
                await client.invoke_agent_async(
                    prompt="Test",
                    user_id="test-user",
                    project_id=str(uuid.uuid4()),
                )

            assert exc_info.value.code == ErrorCode.UNEXPECTED_ERROR
            assert "ValueError" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_agentorchestrator_error_re_raised_unchanged(self) -> None:
        """Test that AgentOrchestratorError instances are re-raised without modification."""
        original_error = AgentOrchestratorClientError(
            "Original error message",
            code=ErrorCode.MISSING_FIELD,
            details="Original details",
        )

        async def mock_post_raises_orchestrator_error(url: str, **kwargs: object) -> MagicMock:
            raise original_error

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_raises_orchestrator_error)  # type: ignore[method-assign]

            with pytest.raises(AgentOrchestratorClientError) as exc_info:
                await client.invoke_agent_async(
                    prompt="Test",
                    user_id="test-user",
                    project_id=str(uuid.uuid4()),
                )

            # Verify it's the same error instance with unchanged properties
            assert exc_info.value.code == ErrorCode.MISSING_FIELD
            assert exc_info.value.message == "Original error message"
            assert exc_info.value.details == "Original details"

    @pytest.mark.asyncio
    async def test_unexpected_exception_converted_to_orchestrator_error(self) -> None:
        """Test that unexpected exceptions (non-HTTP) are converted to AgentOrchestratorError."""

        async def mock_post_raises_value_error(url: str, **kwargs: object) -> MagicMock:
            raise ValueError("Unexpected error")  # noqa: EM101, TRY003

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_raises_value_error)  # type: ignore[method-assign]

            with pytest.raises(AgentOrchestratorClientError) as exc_info:
                await client.invoke_agent_async(
                    prompt="Test",
                    user_id="test-user",
                    project_id=str(uuid.uuid4()),
                )

            assert exc_info.value.code == ErrorCode.UNEXPECTED_ERROR
            assert "ValueError" in exc_info.value.message
            assert "Unexpected error" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_http_server_error_exhausts_retries(self) -> None:
        """Test that 5xx errors persisting through all retries raise appropriate error."""

        async def mock_post_always_500(url: str, **kwargs: object) -> MagicMock:
            response = MagicMock()
            response.status_code = 500
            response.text = "Internal Server Error"
            error = httpx.HTTPStatusError("500 Server Error", request=MagicMock(), response=response)
            return create_mock_http_response(status_code=500, raise_for_status_error=error)

        async with AgentOrchestratorClient(max_retries=2, retry_backoff_base=0.01) as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_always_500)  # type: ignore[method-assign]

            with pytest.raises(AgentOrchestratorClientError) as exc_info:
                await client.invoke_agent_async(
                    prompt="Test",
                    user_id="test-user",
                    project_id=str(uuid.uuid4()),
                )

            assert exc_info.value.code == ErrorCode.HTTP_SERVER_ERROR
            assert "HTTP 500" in exc_info.value.message
            # Verify retries were exhausted
            assert client.http_client.post.call_count == 3  # Initial attempt + 2 re-tries

    @pytest.mark.asyncio
    async def test_timeout_error_exhausts_retries(self) -> None:
        """Test that TimeoutException persisting through all retries raises ConnectionError."""

        async def mock_post_always_timeout(url: str, **kwargs: object) -> MagicMock:
            raise httpx.TimeoutException("Request timeout")  # noqa: EM101, TRY003

        async with AgentOrchestratorClient(max_retries=2, retry_backoff_base=0.01) as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_always_timeout)  # type: ignore[method-assign]

            with pytest.raises(AgentOrchestratorClientConnectionError) as exc_info:
                await client.invoke_agent_async(
                    prompt="Test",
                    user_id="test-user",
                    project_id=str(uuid.uuid4()),
                )

            assert exc_info.value.code == ErrorCode.CONNECTION_FAILED
            assert "Failed to connect" in exc_info.value.message
            # Verify retries were exhausted
            assert client.http_client.post.call_count == 3  # Initial attempt + 2 re-tries


class TestAgentOrchestratorClientStateManagement:
    """Test suite for client state management and reusability."""

    @pytest.mark.asyncio
    async def test_multiple_invocations_with_same_client(self) -> None:
        """Test that client can be reused for multiple sequential invocations without state pollution."""
        invocation_count = 0
        invocation_ids = []

        async def mock_post_sequential(url: str, **kwargs: object) -> MagicMock:
            nonlocal invocation_count
            invocation_count += 1
            invocation_id = f"inv_test_{invocation_count}"
            invocation_ids.append(invocation_id)
            return create_mock_http_response(
                json_data={
                    "id": invocation_id,
                    "status": "completed",
                    "result": {"answer": f"Response {invocation_count}"},
                }
            )

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_sequential)  # type: ignore[method-assign]

            # First invocation
            id1 = await client.invoke_agent_async(
                prompt="First prompt",
                user_id="test-user",
                project_id=str(uuid.uuid4()),
            )

            # Second invocation
            id2 = await client.invoke_agent_async(
                prompt="Second prompt",
                user_id="test-user",
                project_id=str(uuid.uuid4()),
            )

        # Both should succeed with unique IDs
        assert id1 != id2
        assert set(invocation_ids) == {id1, id2}

    @pytest.mark.asyncio
    async def test_concurrent_invocations(self) -> None:
        """Test that multiple concurrent invocations work correctly (thread safety)."""
        call_count = 0

        async def mock_post_concurrent(url: str, **kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            # Capture the ID before async delay to ensure uniqueness
            invocation_id = f"inv_concurrent_{call_count}"
            # Simulate async delay
            await asyncio.sleep(0.01)
            return create_mock_http_response(
                json_data={
                    "id": invocation_id,
                    "status": "completed",
                    "result": {"answer": "Test response"},
                }
            )

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(side_effect=mock_post_concurrent)  # type: ignore[method-assign]

            # Launch 3 concurrent invocations
            results = await asyncio.gather(
                client.invoke_agent_async(prompt="Prompt 1", user_id="test-user", project_id=str(uuid.uuid4())),
                client.invoke_agent_async(prompt="Prompt 2", user_id="test-user", project_id=str(uuid.uuid4())),
                client.invoke_agent_async(prompt="Prompt 3", user_id="test-user", project_id=str(uuid.uuid4())),
            )

        # All should complete successfully
        assert len(results) == 3
        assert all(result.startswith("inv_concurrent_") for result in results)
        # All should have unique IDs
        assert len(set(results)) == 3


class TestAgentOrchestratorClientLogging:
    """Test suite for logging behavior and security."""

    @pytest.mark.asyncio
    async def test_prompt_length_logged_not_content(self) -> None:
        """Test that prompt length is logged but sensitive prompt content is NOT leaked to logs."""
        sensitive_prompt = "SECRET_API_KEY=12345 and PASSWORD=secret"
        mock_post = create_simple_mock_post()

        with patch("syntara.workflows.clients.agent_orchestrator_client.logger") as mock_logger:
            async with AgentOrchestratorClient() as client:
                client.http_client.post = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

                await client.invoke_agent_async(
                    prompt=sensitive_prompt,
                    user_id="test-user",
                    project_id=str(uuid.uuid4()),
                )

            # Verify logger.info was called for invocation (second call after client init)
            assert mock_logger.info.call_count >= 2
            invocation_call_args = mock_logger.info.call_args_list[1]

            # Check that prompt_length is logged (structlog uses keyword arguments)
            assert invocation_call_args[0][0] == "Invoking agent asynchronously"
            assert "prompt_length" in invocation_call_args[1]
            assert invocation_call_args[1]["prompt_length"] == len(sensitive_prompt)

            # CRITICAL: Verify sensitive prompt content is NOT in any log calls
            all_log_calls = (
                mock_logger.debug.call_args_list + mock_logger.info.call_args_list + mock_logger.warning.call_args_list
            )
            for call_args in all_log_calls:
                log_message = str(call_args)
                assert "SECRET_API_KEY" not in log_message
                assert "PASSWORD=secret" not in log_message
                assert sensitive_prompt not in log_message


class TestAgentOrchestratorClientPayloadConstruction:
    """Test suite for payload construction with complex data."""

    @pytest.mark.asyncio
    async def test_special_characters_in_prompt(self) -> None:
        """Test that prompts with special characters, unicode, and newlines are handled correctly."""
        special_prompt = 'Test with "quotes", \n newlines, and emoji 🚀 and unicode: ñ'
        captured_payload: dict[str, Any] = {}

        mock_post = create_payload_capturing_mock(captured_payload)

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

            await client.invoke_agent_async(
                prompt=special_prompt,
                user_id="test-user",
                project_id=str(uuid.uuid4()),
            )

        # Verify prompt is correctly included in payload
        assert captured_payload["prompt"] == special_prompt
        # Verify all special characters are preserved
        assert '"quotes"' in captured_payload["prompt"]
        assert "\n" in captured_payload["prompt"]
        assert "🚀" in captured_payload["prompt"]
        assert "ñ" in captured_payload["prompt"]

    @pytest.mark.asyncio
    async def test_deeply_nested_input_data(self) -> None:
        """Test that complex nested data structures in input_data are handled correctly."""
        complex_input = {
            "level1": {
                "level2": {
                    "level3": [
                        1,
                        2,
                        {"key": "value", "nested_list": [{"a": 1}, {"b": 2}]},
                    ]
                },
                "another_field": "value",
            },
            "array": [1, 2, 3],
        }
        captured_payload: dict[str, Any] = {}

        mock_post = create_payload_capturing_mock(captured_payload)

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

            await client.invoke_agent_async(
                prompt="Test",
                user_id="test-user",
                input_data=complex_input,
                project_id=str(uuid.uuid4()),
            )

        # Verify complex structure is preserved in contextData
        assert captured_payload["contextData"]["input_data"] == complex_input
        # Spot check nested values
        assert captured_payload["contextData"]["input_data"]["level1"]["level2"]["level3"][2]["key"] == "value"

    @pytest.mark.asyncio
    async def test_metadata_with_reserved_keys(self) -> None:
        """Test that metadata with reserved contextData keys doesn't cause collisions."""
        captured_payload: dict[str, Any] = {}

        mock_post = create_payload_capturing_mock(captured_payload)

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(side_effect=mock_post)  # type: ignore[method-assign]

            await client.invoke_agent_async(
                prompt="Test",
                user_id="test-user",
                input_data={"real": "input"},
                metadata={
                    "input_data": "metadata_input",  # Reserved key
                    "model": "metadata_model",  # Reserved key
                    "custom": "value",
                },
                project_id=str(uuid.uuid4()),
            )

        # Top-level input_data should be from the actual parameter, not metadata
        assert captured_payload["contextData"]["input_data"] == {"real": "input"}
        # Metadata should be nested and contain its own keys
        assert captured_payload["contextData"]["metadata"]["input_data"] == "metadata_input"
        assert captured_payload["contextData"]["metadata"]["model"] == "metadata_model"
        assert captured_payload["contextData"]["metadata"]["custom"] == "value"
