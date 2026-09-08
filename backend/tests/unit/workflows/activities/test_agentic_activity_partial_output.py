"""Unit tests for agentic activity partial output (invocation_id early delivery).

Verifies that the agentic activity sends invocation_id as partial output
via Temporal heartbeat immediately after creating the invocation, following
the same pattern as AAP job template activity (PR #265 / bzwei's approach).
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.workflows.workflow_engine.activities.agentic_activity import (
    execute_agentic_activity,
)
from syntara.workflows.workflow_engine.activities.common import (
    HEARTBEAT_PARTIAL_OUTPUT_KEY,
    HEARTBEAT_STOP_MONITOR,
)
from tests.fixtures.temporal import CompleteAsyncError


@pytest.fixture(autouse=True)
def _mock_runtime_settings() -> Generator[None, None, None]:
    mock_cache = AsyncMock()
    mock_cache.get_int = AsyncMock(return_value=100000)
    with patch(
        "syntara.workflows.workflow_engine.activities.agentic_activity.get_runtime_settings",
        return_value=mock_cache,
    ):
        yield


@pytest.fixture
def mock_agent_client() -> AsyncMock:
    mock_instance = AsyncMock()
    mock_instance.invoke_agent_async = AsyncMock(return_value="inv-test-abc")
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=None)
    return mock_instance


@pytest.fixture
def mock_activity_info() -> MagicMock:
    info = MagicMock()
    info.workflow_id = "wf-test-123"
    info.activity_id = "act-test-456"
    return info


@pytest.fixture
def base_input_config() -> dict[str, Any]:
    return {
        "prompt": "Analyze this incident",
        "agent": "generic",
        "model": "test-model",
    }


class TestAgenticActivityPartialOutput:
    """Test that invocation_id is sent as partial output via heartbeat."""

    @pytest.mark.asyncio
    async def test_heartbeat_sends_invocation_id_as_partial_output(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock, base_input_config: dict[str, Any]
    ) -> None:
        execution_id = str(uuid4())
        project_id = str(uuid4())

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient"
            ) as mock_client_cls,
            patch("temporalio.activity.info", return_value=mock_activity_info),
            patch("temporalio.activity.heartbeat") as mock_heartbeat,
            patch("temporalio.activity.raise_complete_async", side_effect=CompleteAsyncError),
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.generate_activity_signal_url",
                return_value="https://example.com/callback",
            ),
        ):
            mock_client_cls.return_value = mock_agent_client

            with pytest.raises(CompleteAsyncError):
                await execute_agentic_activity(
                    input_config=base_input_config,
                    output_config=None,
                    execution_id=execution_id,
                    project_id=project_id,
                )

            assert mock_heartbeat.call_count == 1
            mock_heartbeat.assert_called_once_with(
                {
                    HEARTBEAT_STOP_MONITOR: True,
                    HEARTBEAT_PARTIAL_OUTPUT_KEY: {"invocation_id": "inv-test-abc"},
                }
            )

    @pytest.mark.asyncio
    async def test_partial_output_heartbeat_called_after_invocation_created(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock, base_input_config: dict[str, Any]
    ) -> None:
        """Verify partial output heartbeat is called after invoke_agent_async."""
        execution_id = str(uuid4())
        project_id = str(uuid4())
        call_order: list[str] = []

        async def track_invoke(*_args: object, **_kwargs: object) -> str:
            call_order.append("invoke")
            return "inv-ordered-123"

        mock_agent_client.invoke_agent_async = track_invoke

        def track_heartbeat(*_args: object, **_kwargs: object) -> None:
            call_order.append("heartbeat")

        with (
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient"
            ) as mock_client_cls,
            patch("temporalio.activity.info", return_value=mock_activity_info),
            patch("temporalio.activity.heartbeat", side_effect=track_heartbeat),
            patch("temporalio.activity.raise_complete_async", side_effect=CompleteAsyncError),
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.generate_activity_signal_url",
                return_value="https://example.com/callback",
            ),
        ):
            mock_client_cls.return_value = mock_agent_client

            with pytest.raises(CompleteAsyncError):
                await execute_agentic_activity(
                    input_config=base_input_config,
                    output_config=None,
                    execution_id=execution_id,
                    project_id=project_id,
                )

        assert call_order == ["invoke", "heartbeat"]
