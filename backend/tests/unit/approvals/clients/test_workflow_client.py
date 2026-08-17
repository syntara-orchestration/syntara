"""Unit tests for WorkflowApiClient."""

import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
import respx

from syntara.approvals.clients.workflow_client import WorkflowApiClient


class TestWorkflowApiClient:
    """Test WorkflowApiClient functionality."""

    @pytest.mark.usefixtures("fast_workflow_client_settings")
    async def test_send_approval_signal_success(self) -> None:
        """Test successful approval signal sending."""
        execution_id = uuid4()
        approval_node_id = "approval-node-1"
        decision = "approved"
        approval_id = uuid4()
        decided_by = "jsmith"
        decided_at = "2026-05-20T10:00:00+00:00"
        notes = "Approved by test"

        with patch("syntara.approvals.clients.workflow_client.generate_activity_signal_url") as mock_generate_url:
            mock_generate_url.return_value = "http://localhost:8000/api/v1/signal"

            with respx.mock:
                # Mock successful HTTP response
                signal_route = respx.post("http://localhost:8000/api/v1/signal").mock(return_value=httpx.Response(200))

                async with WorkflowApiClient() as client:
                    await client.send_approval_signal(
                        execution_id=execution_id,
                        approval_node_id=approval_node_id,
                        decision=decision,
                        approval_id=approval_id,
                        decided_by=decided_by,
                        decided_at=decided_at,
                        decision_notes=notes,
                    )

                # Verify the signal URL was generated correctly
                mock_generate_url.assert_called_once_with(execution_id, approval_node_id)

                # Verify the HTTP request was made correctly
                assert signal_route.called
                request = signal_route.calls[0].request
                assert request.method == "POST"
                assert str(request.url) == "http://localhost:8000/api/v1/signal"
                assert request.headers["content-type"] == "application/json"

                # Verify the request payload
                request_json = json.loads(request.content)
                expected_payload = {
                    "signal_data": {
                        "decision": decision,
                        "decided_by": decided_by,
                        "decided_at": decided_at,
                        "decision_notes": notes,
                    }
                }
                assert request_json == expected_payload

    @pytest.mark.usefixtures("fast_workflow_client_settings")
    async def test_send_approval_signal_success_after_retries(self) -> None:
        """Test successful approval signal sending after retries."""
        execution_id = uuid4()
        approval_node_id = "approval-node-1"
        decision = "rejected"
        approval_id = uuid4()

        with patch("syntara.approvals.clients.workflow_client.generate_activity_signal_url") as mock_generate_url:
            mock_generate_url.return_value = "http://localhost:8000/api/v1/signal"

            with respx.mock:
                # First call fails with server error, second succeeds
                signal_route = respx.post("http://localhost:8000/api/v1/signal").mock(
                    side_effect=[
                        httpx.Response(500, text="Server Error"),
                        httpx.Response(200),
                    ]
                )

                with patch("asyncio.sleep") as mock_sleep:
                    async with WorkflowApiClient() as client:
                        await client.send_approval_signal(
                            execution_id=execution_id,
                            approval_node_id=approval_node_id,
                            decision=decision,
                            approval_id=approval_id,
                            decided_by="jsmith",
                            decided_at="2026-05-20T10:00:00+00:00",
                        )

                # Should have made 2 requests (1 failure + 1 success)
                assert len(signal_route.calls) == 2

                # Verify sleep was called for backoff
                mock_sleep.assert_called_once()

    @pytest.mark.usefixtures("fast_workflow_client_settings")
    async def test_send_approval_signal_failure_retries_exhausted(self) -> None:
        """Test approval signal failure after exhausting retries."""
        execution_id = uuid4()
        approval_node_id = "approval-node-1"
        decision = "approved"
        approval_id = uuid4()

        with patch("syntara.approvals.clients.workflow_client.generate_activity_signal_url") as mock_generate_url:
            mock_generate_url.return_value = "http://localhost:8000/api/v1/signal"

            with respx.mock:
                signal_route = respx.post("http://localhost:8000/api/v1/signal").mock(
                    return_value=httpx.Response(500, text="Server Error")
                )

                with patch("asyncio.sleep") as mock_sleep:
                    async with WorkflowApiClient() as client:
                        with pytest.raises(httpx.HTTPStatusError, match="Server Error"):
                            await client.send_approval_signal(
                                execution_id=execution_id,
                                approval_node_id=approval_node_id,
                                decision=decision,
                                approval_id=approval_id,
                                decided_by="jsmith",
                                decided_at="2026-05-20T10:00:00+00:00",
                            )

                # Should have made max_retries + 1 requests (3 in fast settings)
                assert len(signal_route.calls) == 3

                # Should have slept max_retries times (2 times for fast settings)
                assert mock_sleep.call_count == 2

    async def test_send_approval_signal_failure_no_retries(
        self, override_settings: Callable[..., AbstractContextManager[object]]
    ) -> None:
        """Test approval signal failure with max_retries=0."""
        execution_id = uuid4()
        approval_node_id = "approval-node-1"
        decision = "approved"
        approval_id = uuid4()

        with (
            override_settings(workflow_client_max_retries=0),
            patch("syntara.approvals.clients.workflow_client.generate_activity_signal_url") as mock_generate_url,
        ):
            mock_generate_url.return_value = "http://localhost:8000/api/v1/signal"

            with respx.mock:
                signal_route = respx.post("http://localhost:8000/api/v1/signal").mock(
                    return_value=httpx.Response(500, text="Server Error")
                )

                with patch("asyncio.sleep") as mock_sleep:
                    async with WorkflowApiClient() as client:
                        with pytest.raises(httpx.HTTPStatusError, match="Server Error"):
                            await client.send_approval_signal(
                                execution_id=execution_id,
                                approval_node_id=approval_node_id,
                                decision=decision,
                                approval_id=approval_id,
                                decided_by="jsmith",
                                decided_at="2026-05-20T10:00:00+00:00",
                            )

                    # Should have made only 1 request (no retries)
                    assert len(signal_route.calls) == 1

                    # Should not have slept (no retries)
                    mock_sleep.assert_not_called()

    @pytest.mark.usefixtures("fast_workflow_client_settings")
    async def test_send_approval_signal_failure_non_retryable_error(self) -> None:
        """Test approval signal failure with non-retryable error."""
        execution_id = uuid4()
        approval_node_id = "approval-node-1"
        decision = "rejected"
        approval_id = uuid4()

        with patch("syntara.approvals.clients.workflow_client.generate_activity_signal_url") as mock_generate_url:
            mock_generate_url.return_value = "http://localhost:8000/api/v1/signal"

            with respx.mock:
                # Client error (4xx) - not retryable
                signal_route = respx.post("http://localhost:8000/api/v1/signal").mock(
                    return_value=httpx.Response(400, text="Bad Request")
                )

                with patch("asyncio.sleep") as mock_sleep:
                    async with WorkflowApiClient() as client:
                        with pytest.raises(httpx.HTTPStatusError, match="Bad Request"):
                            await client.send_approval_signal(
                                execution_id=execution_id,
                                approval_node_id=approval_node_id,
                                decision=decision,
                                approval_id=approval_id,
                                decided_by="jsmith",
                                decided_at="2026-05-20T10:00:00+00:00",
                            )

                # Should have made only 1 request (no retries for client errors)
                assert len(signal_route.calls) == 1

                # Should not have slept (no retries)
                mock_sleep.assert_not_called()

    async def test_is_retryable_error_server_errors(self) -> None:
        """Test that server errors (5xx) are retryable."""
        async with WorkflowApiClient() as client:
            # 500 Server Error
            response_500 = httpx.Response(500, text="Server Error")
            request = httpx.Request("POST", "http://test")
            server_error = httpx.HTTPStatusError("Server Error", request=request, response=response_500)
            assert client._is_retryable_error(server_error)

            # 502 Bad Gateway
            response_502 = httpx.Response(502, text="Bad Gateway")
            bad_gateway = httpx.HTTPStatusError("Bad Gateway", request=request, response=response_502)
            assert client._is_retryable_error(bad_gateway)

    async def test_is_retryable_error_client_errors(self) -> None:
        """Test that client errors (4xx) are not retryable."""
        async with WorkflowApiClient() as client:
            # 400 Bad Request
            response_400 = httpx.Response(400, text="Bad Request")
            request = httpx.Request("POST", "http://test")
            client_error = httpx.HTTPStatusError("Bad Request", request=request, response=response_400)
            assert not client._is_retryable_error(client_error)

            # 404 Not Found
            response_404 = httpx.Response(404, text="Not Found")
            not_found = httpx.HTTPStatusError("Not Found", request=request, response=response_404)
            assert not client._is_retryable_error(not_found)

    async def test_is_retryable_error_connection_errors(self) -> None:
        """Test that connection and timeout errors are retryable."""
        async with WorkflowApiClient() as client:
            # Connection error
            error_message = "Connection failed"
            connect_error = httpx.ConnectError(error_message)
            assert client._is_retryable_error(connect_error)

            # Timeout error
            error_message = "Request timeout"
            timeout_error = httpx.TimeoutException(error_message)
            assert client._is_retryable_error(timeout_error)

    async def test_is_retryable_error_other_errors(self) -> None:
        """Test that other errors are not retryable."""
        async with WorkflowApiClient() as client:
            # Generic ValueError
            error_message = "Invalid value"
            value_error = ValueError(error_message)
            assert not client._is_retryable_error(value_error)

            # Generic RuntimeError
            error_message = "Runtime error"
            runtime_error = RuntimeError(error_message)
            assert not client._is_retryable_error(runtime_error)

    async def test_context_manager_cleanup(self) -> None:
        """Test that the async context manager properly cleans up HTTP client."""
        with patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            async with WorkflowApiClient() as client:
                assert client.http_client == mock_client

            # Verify the HTTP client was closed
            mock_client.aclose.assert_called_once()
