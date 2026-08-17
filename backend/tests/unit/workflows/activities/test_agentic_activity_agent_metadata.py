"""Unit tests for agentic activity agent metadata handling.

Tests for workflow/execution context propagation to Agent Orchestrator.

These tests verify:
- workflow_id, activity_id, activity_name, execution_id are passed in metadata
- callback_url is passed in metadata when execution_id is provided
- request_id is passed in metadata when provided
- metadata fields are correctly combined with other metadata (credentials, response_schema)
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.workflows.workflow_engine.activities.agentic_activity import (
    execute_agentic_activity,
)
from tests.fixtures.temporal import CompleteAsyncError


@pytest.fixture(autouse=True)
def _mock_heartbeat() -> Generator[None, None, None]:
    """Auto-mock activity.heartbeat() so tests can run outside a Temporal worker."""
    with patch("temporalio.activity.heartbeat"):
        yield


@pytest.fixture
def mock_agent_client() -> AsyncMock:
    """Create a mock Agent Orchestrator client."""
    mock_instance = AsyncMock()
    # New async pattern returns invocation_id immediately
    mock_instance.invoke_agent_async = AsyncMock(return_value="inv_test_123")
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=None)
    return mock_instance


@pytest.fixture
def mock_activity_info() -> MagicMock:
    """Create a mock Temporal activity info."""
    info = MagicMock()
    info.workflow_id = "wf-test-123"
    info.activity_id = "act-test-456"
    return info


class TestAgenticActivityWorkflowContextMetadata:
    """Test suite for workflow/execution context fields in agent metadata."""

    @pytest.mark.asyncio
    async def test_workflow_context_fields_in_metadata(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock
    ) -> None:
        """Test that workflow_id, activity_id, activity_name, execution_id are passed in metadata."""
        execution_id = str(uuid4())
        input_config = {
            "prompt": "Test prompt",
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.generate_activity_signal_url",
                return_value="https://example.com/callback",
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, execution_id=execution_id, project_id=str(uuid4()))

        # Verify invoke_agent_async was called
        mock_agent_client.invoke_agent_async.assert_called_once()

        # Verify workflow context fields are in metadata
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        assert "metadata" in call_kwargs
        metadata = call_kwargs["metadata"]

        assert metadata["workflow_id"] == "wf-test-123"
        assert metadata["activity_id"] == "act-test-456"
        assert metadata["activity_name"] == "agentic_v2"
        assert metadata["execution_id"] == execution_id

    @pytest.mark.asyncio
    async def test_callback_url_in_metadata_when_execution_id_provided(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock
    ) -> None:
        """Test that callback_url is included in metadata when execution_id is provided."""
        execution_id = str(uuid4())
        callback_url = "https://example.com/signal/callback-test"
        input_config = {
            "prompt": "Test prompt",
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.generate_activity_signal_url",
                return_value=callback_url,
            ) as mock_generate_url,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, execution_id=execution_id, project_id=str(uuid4()))

        # Verify callback URL was generated with correct parameters
        from uuid import UUID

        mock_generate_url.assert_called_once_with(UUID(execution_id), "act-test-456")

        # Verify callback_url is in metadata
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        metadata = call_kwargs["metadata"]
        assert "callback_url" in metadata
        assert metadata["callback_url"] == callback_url

    @pytest.mark.asyncio
    async def test_callback_url_not_in_metadata_when_no_execution_id(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock
    ) -> None:
        """Test that callback_url is not included when execution_id is empty."""
        input_config = {
            "prompt": "Test prompt",
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            # execution_id defaults to "" when not provided
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        # Verify callback_url is NOT in metadata
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        metadata = call_kwargs["metadata"]
        assert "callback_url" not in metadata

    @pytest.mark.asyncio
    async def test_request_id_in_metadata_when_provided(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock
    ) -> None:
        """Test that request_id is included in metadata when provided."""
        execution_id = str(uuid4())
        request_id = "req-" + str(uuid4())
        input_config = {
            "prompt": "Test prompt",
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.generate_activity_signal_url",
                return_value="https://example.com/callback",
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(
                input_config, None, execution_id=execution_id, request_id=request_id, project_id=str(uuid4())
            )

        # Verify request_id is in metadata
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        metadata = call_kwargs["metadata"]
        assert "request_id" in metadata
        assert metadata["request_id"] == request_id

    @pytest.mark.asyncio
    async def test_request_id_not_in_metadata_when_none(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock
    ) -> None:
        """Test that request_id is not included in metadata when None."""
        execution_id = str(uuid4())
        input_config = {
            "prompt": "Test prompt",
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.generate_activity_signal_url",
                return_value="https://example.com/callback",
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(
                input_config, None, execution_id=execution_id, request_id=None, project_id=str(uuid4())
            )

        # Verify request_id is NOT in metadata
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        metadata = call_kwargs["metadata"]
        assert "request_id" not in metadata

    @pytest.mark.asyncio
    async def test_metadata_combined_with_credentials(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock
    ) -> None:
        """Test that context metadata is combined with credential metadata."""
        execution_id = str(uuid4())
        request_id = "req-test-123"
        input_config = {
            "prompt": "Test prompt",
            "credentialId": "550e8400-e29b-41d4-a716-446655440000",
            "_resolved_credentials": {
                "credential_id": "550e8400-e29b-41d4-a716-446655440000",
                "extra_vars": {
                    "llm_provider": "openai",
                    "llm_base_url": "https://api.openai.com/v1",
                },
            },
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.generate_activity_signal_url",
                return_value="https://example.com/callback",
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(
                input_config, None, execution_id=execution_id, request_id=request_id, project_id=str(uuid4())
            )

        # Verify both context and credential metadata are present
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        metadata = call_kwargs["metadata"]

        # Context fields
        assert metadata["workflow_id"] == "wf-test-123"
        assert metadata["activity_id"] == "act-test-456"
        assert metadata["activity_name"] == "agentic_v2"
        assert metadata["execution_id"] == execution_id
        assert metadata["callback_url"] == "https://example.com/callback"
        assert metadata["request_id"] == request_id

        # Credential fields
        assert metadata["credential_id"] == "550e8400-e29b-41d4-a716-446655440000"
        assert "llm_provider" not in metadata
        assert "llm_base_url" not in metadata

    @pytest.mark.asyncio
    async def test_metadata_combined_with_response_schema(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock
    ) -> None:
        """Test that context metadata is combined with response_schema."""
        execution_id = str(uuid4())
        schema = {"type": "object", "properties": {"result": {"type": "string"}}}
        input_config = {
            "prompt": "Test prompt",
            "responseSchema": schema,
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.generate_activity_signal_url",
                return_value="https://example.com/callback",
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, execution_id=execution_id, project_id=str(uuid4()))

        # Verify both context and response_schema metadata are present
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        metadata = call_kwargs["metadata"]

        # Context fields
        assert metadata["workflow_id"] == "wf-test-123"
        assert metadata["activity_id"] == "act-test-456"
        assert metadata["activity_name"] == "agentic_v2"
        assert metadata["execution_id"] == execution_id
        assert metadata["callback_url"] == "https://example.com/callback"

        # Response schema
        assert metadata["response_schema"] == schema

    @pytest.mark.asyncio
    async def test_workflow_context_with_direct_invocation(self, mock_agent_client: AsyncMock) -> None:
        """Test that fallback values are used when activity.info() raises RuntimeError."""
        execution_id = str(uuid4())
        input_config = {
            "prompt": "Test prompt",
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                side_effect=RuntimeError("Not in activity context"),
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.generate_activity_signal_url",
                return_value="https://example.com/callback",
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, execution_id=execution_id, project_id=str(uuid4()))

        # Verify fallback values are used
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        metadata = call_kwargs["metadata"]

        assert metadata["workflow_id"] == "direct-invocation"
        assert metadata["activity_id"] == "unknown"
        assert metadata["activity_name"] == "agentic_v2"
        assert metadata["execution_id"] == execution_id

    @pytest.mark.asyncio
    async def test_all_metadata_fields_together(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock
    ) -> None:
        """Test complete metadata with all possible fields populated."""
        execution_id = str(uuid4())
        request_id = "req-complete-test"
        schema: dict[str, Any] = {"type": "string"}
        input_config = {
            "prompt": "Complete test",
            "responseSchema": schema,
            "credentialId": "cred-123",
            "_resolved_credentials": {
                "credential_id": "cred-123",
                "extra_vars": {"llm_provider": "anthropic"},
            },
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.generate_activity_signal_url",
                return_value="https://callback.test",
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(
                input_config, None, execution_id=execution_id, request_id=request_id, project_id=str(uuid4())
            )

        # Verify all metadata fields are present
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        metadata = call_kwargs["metadata"]

        # Workflow context
        assert metadata["workflow_id"] == "wf-test-123"
        assert metadata["activity_id"] == "act-test-456"
        assert metadata["activity_name"] == "agentic_v2"
        assert metadata["execution_id"] == execution_id
        assert metadata["callback_url"] == "https://callback.test"
        assert metadata["request_id"] == request_id

        # Credential
        assert metadata["credential_id"] == "cred-123"
        assert "llm_provider" not in metadata

        # Response schema
        assert metadata["response_schema"] == schema


class TestAgenticActivityIntegrationConnections:
    """Tests for integration_connections metadata propagation."""

    @pytest.mark.asyncio
    async def test_integration_connections_in_metadata_when_configured(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock
    ) -> None:
        """integration_connections are serialized into agent_metadata."""
        integration_id = "550e8400-e29b-41d4-a716-446655440001"
        credential_id = "550e8400-e29b-41d4-a716-446655440002"
        input_config = {
            "prompt": "Test prompt",
            "integration_connections": [{"integration_id": integration_id, "credential_id": credential_id}],
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        metadata = call_kwargs["metadata"]
        assert "integration_connections" in metadata
        assert metadata["integration_connections"] == [
            {"integration_id": integration_id, "credential_id": credential_id}
        ]

    @pytest.mark.asyncio
    async def test_integration_connections_multiple_integrations(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock
    ) -> None:
        """Multiple integration_connections entries are all serialized."""
        connections = [
            {
                "integration_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                "credential_id": "cccccccc-cccc-cccc-cccc-cccccccccccc",
            },
            {
                "integration_id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
                "credential_id": "dddddddd-dddd-dddd-dddd-dddddddddddd",
            },
        ]
        input_config = {"prompt": "Test", "integration_connections": connections}

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        metadata = mock_agent_client.invoke_agent_async.call_args.kwargs["metadata"]
        assert metadata["integration_connections"] == connections

    @pytest.mark.asyncio
    async def test_integration_connections_absent_when_not_configured(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock
    ) -> None:
        """integration_connections key is absent from metadata when not configured."""
        input_config = {"prompt": "Test prompt"}

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        metadata = mock_agent_client.invoke_agent_async.call_args.kwargs["metadata"]
        assert "integration_connections" not in metadata


class TestAgenticActivityToolSelection:
    """Tests for tool_selection_strategy and tool_selections metadata propagation."""

    @pytest.mark.asyncio
    async def test_tool_selections_in_metadata_when_configured(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock
    ) -> None:
        """tool_selection_strategy and tool_selections are injected into agent_metadata."""
        tool_id = "550e8400-e29b-41d4-a716-446655440001"
        input_config = {
            "prompt": "Test prompt",
            "tool_selection_strategy": "SELECTED",
            "tool_selections": [tool_id],
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        metadata = mock_agent_client.invoke_agent_async.call_args.kwargs["metadata"]
        assert metadata["tool_selection_strategy"] == "SELECTED"
        assert metadata["tool_selections"] == [tool_id]

    @pytest.mark.asyncio
    async def test_all_strategy_in_metadata(self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock) -> None:
        """ALL strategy is propagated; tool_selections is absent (not needed for ALL)."""
        input_config = {"prompt": "Test prompt", "tool_selection_strategy": "ALL"}

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        metadata = mock_agent_client.invoke_agent_async.call_args.kwargs["metadata"]
        assert metadata["tool_selection_strategy"] == "ALL"
        assert "tool_selections" not in metadata

    @pytest.mark.asyncio
    async def test_tool_selection_absent_when_not_configured(
        self, mock_agent_client: AsyncMock, mock_activity_info: MagicMock
    ) -> None:
        """Neither key appears in metadata when tool_selection_strategy is absent."""
        input_config = {"prompt": "Test prompt"}

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch(
                "syntara.workflows.workflow_engine.activities.agentic_activity.activity.info",
                return_value=mock_activity_info,
            ),
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        metadata = mock_agent_client.invoke_agent_async.call_args.kwargs["metadata"]
        assert "tool_selection_strategy" not in metadata
        assert "tool_selections" not in metadata
