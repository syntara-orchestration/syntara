"""Unit tests for OrchestrationService._send_completion_callback.

Validates that callback_url is extracted from final_state metadata with
fallback to typed InvocationContextData, preventing duplicate signals.
Also verifies that sensitive URL components (query params, fragments)
are redacted from log output while the full URL is sent to the signal.
"""

from typing import Any, cast
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.models.agent_state import AgentState
from syntara.agent_orchestrator.models.context_data import InvocationContextData
from syntara.agent_orchestrator.services.orchestration_service import OrchestrationService


@pytest.fixture
def orchestration_service() -> OrchestrationService:
    """Create an OrchestrationService with mocked dependencies."""
    with patch.object(OrchestrationService, "__init__", lambda _self: None):
        return OrchestrationService.__new__(OrchestrationService)


def _make_final_state(
    metadata: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
) -> AgentState:
    """Build a minimal final_state dict for testing."""
    return cast(
        "AgentState",
        {
            "prompt": "test",
            "original_prompt": "test",
            "session_id": "s",
            "correlation_id": "c",
            "invocation_id": "i",
            "user_id": None,
            "context_package": None,
            "current_agent": "orchestrator",
            "metadata": metadata,
            "messages": [],
            "result": result,
            "llm_token_usage_log": [],
        },
    )


class TestSendCompletionCallback:
    """Tests for _send_completion_callback callback_url resolution."""

    @pytest.mark.asyncio
    async def test_callback_url_from_final_state_metadata(self, orchestration_service: OrchestrationService) -> None:
        """When final_state has metadata.callback_url, use it."""
        callback_url = "http://nexus/signal/activity/123"
        invocation_id = uuid4()
        final_state = _make_final_state(
            metadata={"callback_url": callback_url},
            result={"content": "done"},
        )

        with patch(
            "syntara.agent_orchestrator.services.orchestration_service.WorkflowSignalClient.send_success_signal",
            new_callable=AsyncMock,
        ) as mock_signal:
            await orchestration_service._send_completion_callback(final_state, invocation_id)
            mock_signal.assert_awaited_once_with(callback_url, invocation_id, {"content": "done"})

    @pytest.mark.asyncio
    async def test_callback_url_falls_back_to_ctx(self, orchestration_service: OrchestrationService) -> None:
        """When final_state has no metadata, fall back to typed ctx."""
        callback_url = "http://nexus/signal/activity/456"
        invocation_id = uuid4()
        final_state = _make_final_state(
            metadata=None,
            result={"content": "done"},
        )
        ctx = InvocationContextData.model_validate({"callback_url": callback_url})

        with patch(
            "syntara.agent_orchestrator.services.orchestration_service.WorkflowSignalClient.send_success_signal",
            new_callable=AsyncMock,
        ) as mock_signal:
            await orchestration_service._send_completion_callback(final_state, invocation_id, ctx)
            mock_signal.assert_awaited_once_with(callback_url, invocation_id, {"content": "done"})

    @pytest.mark.asyncio
    async def test_final_state_metadata_takes_precedence(self, orchestration_service: OrchestrationService) -> None:
        """When both sources have callback_url, final_state wins."""
        invocation_id = uuid4()
        final_state = _make_final_state(
            metadata={"callback_url": "http://from-state"},
            result={"content": "done"},
        )
        ctx = InvocationContextData.model_validate({"callback_url": "http://from-original"})

        with patch(
            "syntara.agent_orchestrator.services.orchestration_service.WorkflowSignalClient.send_success_signal",
            new_callable=AsyncMock,
        ) as mock_signal:
            await orchestration_service._send_completion_callback(final_state, invocation_id, ctx)
            mock_signal.assert_awaited_once_with("http://from-state", invocation_id, {"content": "done"})

    @pytest.mark.asyncio
    async def test_no_callback_url_skips_signal(self, orchestration_service: OrchestrationService) -> None:
        """When neither source has callback_url, no signal is sent."""
        invocation_id = uuid4()
        final_state = _make_final_state(metadata=None, result={"content": "done"})

        with patch(
            "syntara.agent_orchestrator.services.orchestration_service.WorkflowSignalClient.send_success_signal",
            new_callable=AsyncMock,
        ) as mock_signal:
            await orchestration_service._send_completion_callback(final_state, invocation_id)
            mock_signal.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_result_skips_signal(self, orchestration_service: OrchestrationService) -> None:
        """When final_state has no result, no signal is sent."""
        invocation_id = uuid4()
        final_state = _make_final_state(
            metadata={"callback_url": "http://nexus/signal"},
            result=None,
        )

        with patch(
            "syntara.agent_orchestrator.services.orchestration_service.WorkflowSignalClient.send_success_signal",
            new_callable=AsyncMock,
        ) as mock_signal:
            await orchestration_service._send_completion_callback(final_state, invocation_id)
            mock_signal.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_metadata_in_final_state_falls_back(self, orchestration_service: OrchestrationService) -> None:
        """When final_state metadata is {} (no callback_url), fall back."""
        callback_url = "http://nexus/signal/activity/789"
        invocation_id = uuid4()
        final_state = _make_final_state(
            metadata={},
            result={"content": "done"},
        )
        ctx = InvocationContextData.model_validate({"callback_url": callback_url})

        with patch(
            "syntara.agent_orchestrator.services.orchestration_service.WorkflowSignalClient.send_success_signal",
            new_callable=AsyncMock,
        ) as mock_signal:
            await orchestration_service._send_completion_callback(final_state, invocation_id, ctx)
            mock_signal.assert_awaited_once_with(callback_url, invocation_id, {"content": "done"})

    @pytest.mark.asyncio
    async def test_used_tools_attached_without_mutating_result(
        self, orchestration_service: OrchestrationService
    ) -> None:
        """used_tools is included in the signal payload without mutating shared result."""
        callback_url = "http://nexus/signal/activity/tools"
        invocation_id = uuid4()
        shared_result: dict[str, Any] = {"content": "done"}
        final_state = _make_final_state(
            metadata={"callback_url": callback_url},
            result=shared_result,
        )

        with (
            patch(
                "syntara.agent_orchestrator.services.orchestration_service.aggregate_used_tools",
                return_value=[{"name": "search", "count": 2}, {"name": "fetch", "count": 1}],
            ),
            patch(
                "syntara.agent_orchestrator.services.orchestration_service.WorkflowSignalClient.send_success_signal",
                new_callable=AsyncMock,
            ) as mock_signal,
        ):
            await orchestration_service._send_completion_callback(final_state, invocation_id)

        mock_signal.assert_awaited_once_with(
            callback_url,
            invocation_id,
            {
                "content": "done",
                "used_tools": [{"name": "search", "count": 2}, {"name": "fetch", "count": 1}],
            },
        )
        assert "used_tools" not in shared_result
        assert final_state["result"] is shared_result


class TestCallbackUrlRedaction:
    """Tests for callback_url redaction in log output."""

    @pytest.mark.asyncio
    async def test_query_params_redacted_from_log(self, orchestration_service: OrchestrationService) -> None:
        """Query parameters are stripped from the logged URL but the full URL is sent to the signal."""
        callback_url = "http://nexus/signal/activity/123?token=secret&session=abc"
        invocation_id = uuid4()
        final_state = _make_final_state(
            metadata={"callback_url": callback_url},
            result={"content": "done"},
        )

        with (
            patch(
                "syntara.agent_orchestrator.services.orchestration_service.WorkflowSignalClient.send_success_signal",
                new_callable=AsyncMock,
            ) as mock_signal,
            patch("syntara.agent_orchestrator.services.orchestration_service.logger") as mock_logger,
        ):
            await orchestration_service._send_completion_callback(final_state, invocation_id)

            mock_signal.assert_awaited_once_with(callback_url, invocation_id, {"content": "done"})

            info_calls = [c for c in mock_logger.info.call_args_list if "Sending callback" in str(c)]
            assert len(info_calls) == 1
            logged_url = info_calls[0].kwargs["callback_url"]
            assert "token=secret" not in logged_url
            assert "session=abc" not in logged_url
            assert logged_url == "http://nexus/signal/activity/123"

    @pytest.mark.asyncio
    async def test_fragment_redacted_from_log(self, orchestration_service: OrchestrationService) -> None:
        """Fragments are stripped from the logged URL."""
        callback_url = "http://nexus/signal/activity/123#sensitive-anchor"
        invocation_id = uuid4()
        final_state = _make_final_state(
            metadata={"callback_url": callback_url},
            result={"content": "done"},
        )

        with (
            patch(
                "syntara.agent_orchestrator.services.orchestration_service.WorkflowSignalClient.send_success_signal",
                new_callable=AsyncMock,
            ) as mock_signal,
            patch("syntara.agent_orchestrator.services.orchestration_service.logger") as mock_logger,
        ):
            await orchestration_service._send_completion_callback(final_state, invocation_id)

            mock_signal.assert_awaited_once_with(callback_url, invocation_id, {"content": "done"})

            info_calls = [c for c in mock_logger.info.call_args_list if "Sending callback" in str(c)]
            logged_url = info_calls[0].kwargs["callback_url"]
            assert "sensitive-anchor" not in logged_url
            assert logged_url == "http://nexus/signal/activity/123"

    @pytest.mark.asyncio
    async def test_query_and_fragment_both_redacted(self, orchestration_service: OrchestrationService) -> None:
        """Both query params and fragments are stripped from the logged URL."""
        callback_url = "http://nexus/signal/activity/123?key=val#frag"
        invocation_id = uuid4()
        final_state = _make_final_state(
            metadata={"callback_url": callback_url},
            result={"content": "done"},
        )

        with (
            patch(
                "syntara.agent_orchestrator.services.orchestration_service.WorkflowSignalClient.send_success_signal",
                new_callable=AsyncMock,
            ) as mock_signal,
            patch("syntara.agent_orchestrator.services.orchestration_service.logger") as mock_logger,
        ):
            await orchestration_service._send_completion_callback(final_state, invocation_id)

            mock_signal.assert_awaited_once_with(callback_url, invocation_id, {"content": "done"})

            info_calls = [c for c in mock_logger.info.call_args_list if "Sending callback" in str(c)]
            logged_url = info_calls[0].kwargs["callback_url"]
            assert logged_url == "http://nexus/signal/activity/123"

    @pytest.mark.asyncio
    async def test_url_without_sensitive_parts_logged_unchanged(
        self, orchestration_service: OrchestrationService
    ) -> None:
        """A plain URL with no query or fragment is logged as-is."""
        callback_url = "http://nexus/signal/activity/123"
        invocation_id = uuid4()
        final_state = _make_final_state(
            metadata={"callback_url": callback_url},
            result={"content": "done"},
        )

        with (
            patch(
                "syntara.agent_orchestrator.services.orchestration_service.WorkflowSignalClient.send_success_signal",
                new_callable=AsyncMock,
            ),
            patch("syntara.agent_orchestrator.services.orchestration_service.logger") as mock_logger,
        ):
            await orchestration_service._send_completion_callback(final_state, invocation_id)

            info_calls = [c for c in mock_logger.info.call_args_list if "Sending callback" in str(c)]
            logged_url = info_calls[0].kwargs["callback_url"]
            assert logged_url == callback_url
