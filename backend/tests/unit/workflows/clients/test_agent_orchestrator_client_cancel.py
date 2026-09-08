"""Tests for AgentOrchestratorClient cancel and timeout features."""

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from syntara.workflows.clients.agent_orchestrator_client import (
    AgentOrchestratorClient,
)


def create_mock_http_response(
    json_data: dict[str, Any] | None = None,
    status_code: int = 200,
    raise_for_status_error: Exception | None = None,
) -> MagicMock:
    """Create a mock HTTP response object."""
    response = MagicMock()
    response.json.return_value = json_data if json_data is not None else {}
    response.status_code = status_code
    if raise_for_status_error:
        response.raise_for_status.side_effect = raise_for_status_error
    else:
        response.raise_for_status = MagicMock()
    return response


def create_payload_capturing_mock(
    captured_payload: dict[str, Any],
    response: MagicMock | None = None,
) -> AsyncMock:
    """Create a mock POST function that captures payload and returns a response."""

    async def mock_post(url: str, **kwargs: object) -> MagicMock:
        json_data = kwargs.get("json", {})
        if isinstance(json_data, dict):
            captured_payload.clear()
            captured_payload.update(json_data)
        return response or create_mock_http_response(json_data={"id": "inv_test_123", "status": "created"})

    return AsyncMock(side_effect=mock_post)


class TestCancelInvocation:
    """Tests for cancel_invocation method."""

    @pytest.mark.asyncio
    async def test_cancel_invocation_posts_to_correct_url(self) -> None:
        """Verify POST to /invocations/{id}/cancel."""
        invocation_id = str(uuid.uuid4())

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(  # type: ignore[method-assign]
                return_value=create_mock_http_response()
            )

            await client.cancel_invocation(invocation_id)

            client.http_client.post.assert_called_once()
            call_args = client.http_client.post.call_args
            assert call_args[0][0] == f"/invocations/{invocation_id}/cancel"

    @pytest.mark.asyncio
    async def test_cancel_invocation_sends_reason(self) -> None:
        """Verify JSON body has the reason."""
        invocation_id = str(uuid.uuid4())
        reason = "User requested cancellation"

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(  # type: ignore[method-assign]
                return_value=create_mock_http_response()
            )

            await client.cancel_invocation(invocation_id, reason=reason)

            call_kwargs = client.http_client.post.call_args[1]
            assert call_kwargs["json"] == {"reason": reason}

    @pytest.mark.asyncio
    async def test_cancel_invocation_swallows_errors(self) -> None:
        """No exception raised on HTTP error."""
        invocation_id = str(uuid.uuid4())

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        error = httpx.HTTPStatusError(
            "Server error",
            request=MagicMock(),
            response=mock_response,
        )

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(  # type: ignore[method-assign]
                return_value=create_mock_http_response(raise_for_status_error=error)
            )

            # Should not raise
            await client.cancel_invocation(invocation_id)

    @pytest.mark.asyncio
    async def test_cancel_invocation_uses_default_reason(self) -> None:
        """Default reason is 'Workflow timeout'."""
        invocation_id = str(uuid.uuid4())

        async with AgentOrchestratorClient() as client:
            client.http_client.post = AsyncMock(  # type: ignore[method-assign]
                return_value=create_mock_http_response()
            )

            await client.cancel_invocation(invocation_id)

            call_kwargs = client.http_client.post.call_args[1]
            assert call_kwargs["json"] == {"reason": "Workflow timeout"}


class TestTimeoutInPayload:
    """Tests for timeout_seconds in invocation payload."""

    @pytest.mark.asyncio
    async def test_timeout_seconds_in_context_data(self) -> None:
        """timeout_seconds=60 appears in contextData."""
        captured_payload: dict[str, Any] = {}

        async with AgentOrchestratorClient() as client:
            client.http_client.post = create_payload_capturing_mock(captured_payload)  # type: ignore[method-assign]

            await client.invoke_agent_async(
                prompt="Test prompt",
                user_id="test-user",
                project_id=str(uuid.uuid4()),
                timeout_seconds=60,
            )

        assert "contextData" in captured_payload
        assert captured_payload["contextData"]["timeout_seconds"] == 60

    @pytest.mark.asyncio
    async def test_timeout_seconds_omitted_when_none(self) -> None:
        """timeout_seconds not in contextData when None."""
        captured_payload: dict[str, Any] = {}

        async with AgentOrchestratorClient() as client:
            client.http_client.post = create_payload_capturing_mock(captured_payload)  # type: ignore[method-assign]

            await client.invoke_agent_async(
                prompt="Test prompt",
                user_id="test-user",
                project_id=str(uuid.uuid4()),
                timeout_seconds=None,
            )

        assert "contextData" in captured_payload
        assert "timeout_seconds" not in captured_payload["contextData"]
