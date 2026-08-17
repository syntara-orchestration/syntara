"""Unit tests for agentic activity response_schema handling.

Tests for structured output support in agentic nodes.

These tests verify:
- response_schema is extracted from config correctly
- response_schema is passed to Agent Orchestrator in metadata
- response_schema can be None (optional)
- response_schema validation works correctly
"""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from temporalio.exceptions import ApplicationError

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


class TestAgenticActivityResponseSchema:
    """Test suite for response_schema handling in execute_agentic_activity."""

    @pytest.mark.asyncio
    async def test_response_schema_passed_in_metadata(self, mock_agent_client: AsyncMock) -> None:
        """Test that response_schema is correctly passed in metadata."""
        schema = {
            "type": "object",
            "properties": {
                "hostname": {"type": "string"},
                "ip_address": {"type": "string"},
            },
            "required": ["hostname"],
        }
        input_config = {
            "prompt": "Extract server info",
            "responseSchema": schema,
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        # Verify invoke_agent_async was called
        mock_agent_client.invoke_agent_async.assert_called_once()

        # Verify response_schema was passed in metadata
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        assert "metadata" in call_kwargs
        assert "response_schema" in call_kwargs["metadata"]
        assert call_kwargs["metadata"]["response_schema"] == schema

    @pytest.mark.asyncio
    async def test_response_schema_not_in_metadata_when_none(self, mock_agent_client: AsyncMock) -> None:
        """Test that response_schema is not in metadata when None."""
        input_config = {
            "prompt": "Process without schema",
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        # Verify response_schema is NOT in metadata when None
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        assert "metadata" in call_kwargs
        assert "response_schema" not in call_kwargs["metadata"]

    @pytest.mark.asyncio
    async def test_response_schema_simple_type(self, mock_agent_client: AsyncMock) -> None:
        """Test that simple schema types are passed correctly."""
        schema = {"type": "string"}
        input_config = {
            "prompt": "Return a string",
            "responseSchema": schema,
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        assert call_kwargs["metadata"]["response_schema"] == schema

    @pytest.mark.asyncio
    async def test_response_schema_array_type(self, mock_agent_client: AsyncMock) -> None:
        """Test that array schemas are passed correctly."""
        schema = {
            "type": "array",
            "items": {"type": "string"},
        }
        input_config = {
            "prompt": "Return a list of hostnames",
            "responseSchema": schema,
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        assert call_kwargs["metadata"]["response_schema"] == schema

    @pytest.mark.asyncio
    async def test_response_schema_complex_nested(self, mock_agent_client: AsyncMock) -> None:
        """Test that complex nested schemas are passed correctly."""
        schema = {
            "type": "object",
            "properties": {
                "servers": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "hostname": {"type": "string"},
                            "status": {"type": "string", "enum": ["running", "stopped"]},
                        },
                        "required": ["hostname", "status"],
                    },
                },
                "count": {"type": "integer"},
            },
            "required": ["servers"],
        }
        input_config = {
            "prompt": "Return server status",
            "responseSchema": schema,
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        assert call_kwargs["metadata"]["response_schema"] == schema

    @pytest.mark.asyncio
    async def test_response_schema_with_other_fields(self, mock_agent_client: AsyncMock) -> None:
        """Test that response_schema works alongside other config fields."""
        schema = {"type": "object", "properties": {"result": {"type": "string"}}}
        llm_model_id = "550e8400-e29b-41d4-a716-446655440000"
        input_config = {
            "prompt": "Analyze data",
            "agent": "analyzer",
            "llm_model_id": llm_model_id,
            "timeout": 300,
            "responseSchema": schema,
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        assert call_kwargs["prompt"] == "Analyze data"
        assert call_kwargs["agent"] == "analyzer"
        assert call_kwargs["metadata"]["response_schema"] == schema
        assert call_kwargs["metadata"]["llm_model_id"] == llm_model_id

    @pytest.mark.asyncio
    async def test_response_schema_invalid_rejected(self) -> None:
        """Test that invalid response_schema is rejected during validation."""
        input_config = {
            "prompt": "Test",
            "responseSchema": {"type": "object", "properties": {"data": {"$ref": "https://evil.com/schema"}}},
        }

        with pytest.raises(ApplicationError) as exc_info:
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))
        assert exc_info.value.type == "ConfigError"

    @pytest.mark.asyncio
    async def test_response_schema_template_expression(self, mock_agent_client: AsyncMock) -> None:
        """Test that template expressions bypass validation and are passed through."""
        template = "${trigger.schema}"
        input_config = {
            "prompt": "Use dynamic schema",
            "responseSchema": template,
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        # Template expressions are passed through to metadata
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        assert call_kwargs["metadata"]["response_schema"] == template

    @pytest.mark.asyncio
    async def test_response_schema_metadata_order(self, mock_agent_client: AsyncMock) -> None:
        """Test that response_schema is added to metadata after credential injection."""
        schema = {"type": "string"}
        input_config = {
            "prompt": "Test",
            "responseSchema": schema,
            "credentialId": "550e8400-e29b-41d4-a716-446655440000",
            "_resolved_credentials": {
                "credential_id": "550e8400-e29b-41d4-a716-446655440000",
                "extra_vars": {
                    "llm_provider": "openai",
                },
            },
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid4()))

        # Verify both credential and response_schema are in metadata
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        metadata = call_kwargs["metadata"]
        assert "credential_id" in metadata
        assert "llm_provider" not in metadata
        assert "response_schema" in metadata
        assert metadata["response_schema"] == schema
