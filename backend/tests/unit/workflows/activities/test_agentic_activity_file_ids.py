"""Unit tests for agentic activity file_ids handling.

Tests for AAP-60786 - Agentic Activity file_ids Integration.

These tests verify:
- file_ids are extracted from config correctly
- file_ids are passed to Agent Orchestrator as a dedicated parameter
- file_ids validation (max count, format, etc.)
"""

import uuid
from collections.abc import Generator
from unittest.mock import AsyncMock, patch

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


def generate_valid_uuid() -> str:
    """Generate a valid UUID string."""
    return str(uuid.uuid4())


def generate_valid_uuids(count: int) -> list[str]:
    """Generate a list of valid UUID strings."""
    return [generate_valid_uuid() for _ in range(count)]


@pytest.fixture
def mock_agent_client() -> AsyncMock:
    """Create a mock Agent Orchestrator client."""
    mock_instance = AsyncMock()
    # New async pattern returns invocation_id immediately
    mock_instance.invoke_agent_async = AsyncMock(return_value="inv_test_123")
    mock_instance.__aenter__ = AsyncMock(return_value=mock_instance)
    mock_instance.__aexit__ = AsyncMock(return_value=None)
    return mock_instance


class TestAgenticActivityFileIds:
    """Test suite for file_ids handling in execute_agentic_activity."""

    @pytest.mark.asyncio
    async def test_file_ids_extracted_from_config(self, mock_agent_client: AsyncMock) -> None:
        """Test that file_ids are correctly extracted from config and passed as parameter."""
        file_ids = generate_valid_uuids(3)
        input_config = {
            "prompt": "Analyze these files",
            "file_ids": file_ids,
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid.uuid4()))

        mock_agent_client.invoke_agent_async.assert_called_once()
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        assert "file_ids" in call_kwargs
        assert call_kwargs["file_ids"] == file_ids

    @pytest.mark.asyncio
    async def test_file_ids_empty_when_not_specified(self, mock_agent_client: AsyncMock) -> None:
        """Test that when no file_ids specified, empty list is passed as parameter."""
        input_config = {
            "prompt": "Process without files",
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid.uuid4()))

        # Verify file_ids was passed as empty list parameter
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        assert "file_ids" in call_kwargs
        assert call_kwargs["file_ids"] == []

    @pytest.mark.asyncio
    async def test_file_ids_passed_as_separate_parameter(self, mock_agent_client: AsyncMock) -> None:
        """Test that file_ids are passed as separate parameter, not merged with input_data."""
        file_ids = generate_valid_uuids(2)
        input_config = {
            "prompt": "Process with context",
            "file_ids": file_ids,
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid.uuid4()))

        # Verify file_ids passed as separate parameter
        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        assert "file_ids" in call_kwargs
        assert call_kwargs["file_ids"] == file_ids

    @pytest.mark.asyncio
    async def test_file_ids_max_count_accepted(self, mock_agent_client: AsyncMock) -> None:
        """Test that maximum 10 file_ids are accepted and passed correctly as parameter."""
        file_ids = generate_valid_uuids(10)
        input_config = {
            "prompt": "Process all 10 files",
            "file_ids": file_ids,
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid.uuid4()))

        call_kwargs = mock_agent_client.invoke_agent_async.call_args.kwargs
        assert "file_ids" in call_kwargs
        assert len(call_kwargs["file_ids"]) == 10

    @pytest.mark.asyncio
    async def test_file_ids_invalid_rejected_during_config_validation(self) -> None:
        """Test that invalid file_ids are rejected during config validation."""
        input_config = {
            "prompt": "Test",
            "file_ids": ["not-a-valid-uuid"],
        }

        with pytest.raises(ApplicationError) as exc_info:
            await execute_agentic_activity(input_config, None, project_id=str(uuid.uuid4()))
        err = str(exc_info.value).lower()
        assert "invalid" in err or "file_id" in err

    @pytest.mark.asyncio
    async def test_file_ids_too_many_rejected(self) -> None:
        """Test that more than 10 file_ids are rejected."""
        input_config = {
            "prompt": "Test",
            "file_ids": generate_valid_uuids(11),
        }

        with pytest.raises(ApplicationError):
            await execute_agentic_activity(input_config, None, project_id=str(uuid.uuid4()))

    @pytest.mark.asyncio
    async def test_file_count_logged(self, mock_agent_client: AsyncMock) -> None:
        """Test that file count is logged for observability."""
        file_ids = generate_valid_uuids(5)
        input_config = {
            "prompt": "Test",
            "file_ids": file_ids,
        }

        with (
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.AgentOrchestratorClient") as mock_cls,
            patch("syntara.workflows.workflow_engine.activities.agentic_activity.logger") as mock_logger,
            pytest.raises(CompleteAsyncError),
        ):
            mock_cls.return_value = mock_agent_client
            await execute_agentic_activity(input_config, None, project_id=str(uuid.uuid4()))

        # Verify logging includes file_count as a keyword argument
        info_calls = mock_logger.info.call_args_list
        found_file_count_log = False
        for call in info_calls:
            kwargs = call[1]  # Keyword arguments
            if kwargs.get("file_count") == 5:
                found_file_count_log = True
                break
        assert found_file_count_log, f"Expected file_count=5 in log calls: {info_calls}"
