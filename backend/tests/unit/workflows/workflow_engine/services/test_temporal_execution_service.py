"""Unit tests for TemporalExecutionService.

These tests use mocks to avoid requiring a real Temporal server.
Integration tests with a real Temporal server are in tests/integration/.
"""

from typing import Any
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID

import pytest
import yaml

from syntara.core.config.base import get_settings
from syntara.core.exceptions import SafeValueError
from syntara.workflows.workflow_engine.services.temporal_execution_service import (
    TemporalExecutionService,
    create_temporal_execution_service,
)


@pytest.fixture
def valid_workflow_dict() -> dict[str, Any]:
    """Fixture providing a valid V2 workflow definition as dict."""
    return {
        "schema_version": "2.0.0",
        "name": "test-workflow",
        "description": "Test",
        "triggers": [{"id": "trigger_manual", "type": "manual_trigger"}],
        "nodes": [
            {
                "id": "task1",
                "type": "script",
                "parameters": {"language": "bash", "code": "echo test"},
            }
        ],
        "edges": [{"from": "trigger_manual", "to": "task1"}],
    }


@pytest.fixture
def valid_workflow_yaml(valid_workflow_dict: dict[str, Any]) -> str:
    """Fixture providing a valid workflow definition as YAML string."""
    return yaml.dump(valid_workflow_dict)


class TestTemporalExecutionServiceInitialization:
    """Test TemporalExecutionService initialization."""

    def test_init_with_client(self) -> None:
        """Test initialization with Temporal client."""
        mock_client = Mock()
        service = TemporalExecutionService(temporal_client=mock_client, task_queue="test-queue")

        assert service.temporal_client is mock_client
        assert service.task_queue == "test-queue"

    def test_init_with_custom_task_queue(self) -> None:
        """Test initialization with custom task queue."""
        mock_client = Mock()
        service = TemporalExecutionService(temporal_client=mock_client, task_queue="custom-queue")

        assert service.temporal_client is mock_client
        assert service.task_queue == "custom-queue"


class TestStartWorkflow:
    """Test starting workflows from dict format."""

    @pytest.mark.asyncio
    async def test_start_workflow_success(
        self,
        valid_workflow_dict: dict[str, Any],
    ) -> None:
        """Test successfully starting a workflow."""
        # Mock Temporal client
        mock_client = Mock()
        mock_handle = Mock()
        mock_handle.first_execution_run_id = "run-123"
        mock_client.start_workflow = AsyncMock(return_value=mock_handle)

        service = TemporalExecutionService(temporal_client=mock_client, task_queue="test-queue")

        result = await service.start_workflow(
            workflow_def=valid_workflow_dict,
            workflow_name="test-workflow",
            input_data={"user_id": 123},
            trigger_node_id="trigger_manual",
        )

        # Verify result structure (Pydantic model)
        assert result.execution_id is not None
        assert result.workflow_id is not None
        assert result.temporal_workflow_id is not None
        assert result.temporal_run_id is not None
        assert result.status is not None
        assert result.started_at is not None

        # Verify values
        assert result.temporal_run_id == "run-123"
        assert result.status == "running"
        assert "test-workflow" in result.temporal_workflow_id

        # Verify UUID formats
        UUID(result.execution_id)
        UUID(result.workflow_id)

        # Verify Temporal client was called
        mock_client.start_workflow.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_workflow_with_custom_id(
        self,
        valid_workflow_dict: dict[str, Any],
    ) -> None:
        """Test starting workflow with custom workflow ID."""
        mock_client = Mock()
        mock_handle = Mock()
        mock_handle.first_execution_run_id = "run-456"
        mock_client.start_workflow = AsyncMock(return_value=mock_handle)

        service = TemporalExecutionService(temporal_client=mock_client, task_queue="test-queue")

        result = await service.start_workflow(
            workflow_def=valid_workflow_dict,
            workflow_name="test-workflow",
            workflow_id="custom-workflow-id",
            trigger_node_id="trigger_manual",
        )

        assert result.workflow_id == "custom-workflow-id"

    @pytest.mark.asyncio
    async def test_start_workflow_temporal_error(
        self,
        valid_workflow_dict: dict[str, Any],
    ) -> None:
        """Test starting workflow when Temporal fails."""
        mock_client = Mock()
        mock_client.start_workflow = AsyncMock(side_effect=RuntimeError("Temporal connection failed"))

        service = TemporalExecutionService(temporal_client=mock_client, task_queue="test-queue")

        with pytest.raises(RuntimeError, match="Temporal connection failed"):
            await service.start_workflow(
                workflow_def=valid_workflow_dict,
                workflow_name="test-workflow",
                trigger_node_id="trigger_manual",
            )

    @pytest.mark.asyncio
    async def test_start_workflow_invalid_definition(self) -> None:
        """Test starting workflow with dict missing required fields."""
        mock_client = Mock()
        service = TemporalExecutionService(temporal_client=mock_client, task_queue="test-queue")

        # Invalid dict missing required V2 fields (no schema_version)
        invalid_dict = {"schema_version": "1.0.0"}

        with pytest.raises(SafeValueError, match="Unsupported schema_version"):
            await service.start_workflow(
                workflow_def=invalid_dict,
                workflow_name="test-workflow",
                trigger_node_id="irrelevant",
            )

    @pytest.mark.asyncio
    async def test_start_workflow_requires_trigger_node_id(self) -> None:
        """Test that start_workflow uses the explicitly provided trigger_node_id."""
        multi_trigger_workflow = {
            "schema_version": "2.0.0",
            "name": "multi-trigger-workflow",
            "triggers": [
                {"id": "eda_1", "type": "eda_trigger", "parameters": {"webhook_path": "my-hook"}},
                {"id": "manual_1", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [],
            "edges": [],
        }

        mock_client = Mock()
        mock_handle = Mock()
        mock_handle.first_execution_run_id = "run-789"
        mock_client.start_workflow = AsyncMock(return_value=mock_handle)

        service = TemporalExecutionService(temporal_client=mock_client, task_queue="test-queue")

        await service.start_workflow(
            workflow_def=multi_trigger_workflow,
            workflow_name="multi-trigger-workflow",
            trigger_node_id="eda_1",
        )

        call_kwargs = mock_client.start_workflow.call_args
        temporal_args = call_kwargs.kwargs.get("args") or call_kwargs[1].get("args")
        trigger_node_id_arg = temporal_args[2]
        assert trigger_node_id_arg == "eda_1"


class TestTriggerSelection:
    """Test trigger node selection logic for multi-trigger workflows."""

    # NexusWorkflow.run signature: (workflow_def, execution_id, trigger_node_id, ...)
    TRIGGER_NODE_ID_ARG_INDEX = 2

    def _get_trigger_node_id_from_call(self, mock_client: Mock) -> str:
        """Extract trigger_node_id passed to NexusWorkflow.run from the mock call."""
        call_kwargs = mock_client.start_workflow.call_args
        temporal_args = call_kwargs.kwargs.get("args") or call_kwargs[1].get("args")
        expected_min = self.TRIGGER_NODE_ID_ARG_INDEX + 1
        assert len(temporal_args) >= expected_min, (
            f"Expected at least {expected_min} args to NexusWorkflow.run, got {len(temporal_args)}"
        )
        return str(temporal_args[self.TRIGGER_NODE_ID_ARG_INDEX])

    @pytest.mark.asyncio
    async def test_start_workflow_with_explicit_trigger_node_id(self) -> None:
        """When trigger_node_id is specified, use that trigger."""
        multi_trigger_workflow = {
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "manual_1", "type": "manual_trigger", "parameters": {}},
                {"id": "manual_2", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [],
            "edges": [],
        }

        mock_client = Mock()
        mock_handle = Mock()
        mock_handle.first_execution_run_id = "run-202"
        mock_client.start_workflow = AsyncMock(return_value=mock_handle)

        service = TemporalExecutionService(temporal_client=mock_client, task_queue="test-queue")

        await service.start_workflow(
            workflow_def=multi_trigger_workflow,
            workflow_name="multi-trigger-workflow",
            trigger_node_id="manual_2",
        )

        assert self._get_trigger_node_id_from_call(mock_client) == "manual_2"

    @pytest.mark.asyncio
    async def test_start_workflow_with_invalid_trigger_node_id(self) -> None:
        """When trigger_node_id doesn't exist in workflow, raise SafeValueError."""
        workflow_def = {
            "schema_version": "2.0.0",
            "triggers": [
                {"id": "manual_1", "type": "manual_trigger", "parameters": {}},
            ],
            "nodes": [],
            "edges": [],
        }

        mock_client = Mock()
        service = TemporalExecutionService(temporal_client=mock_client, task_queue="test-queue")

        with pytest.raises(SafeValueError, match="not found in workflow triggers"):
            await service.start_workflow(
                workflow_def=workflow_def,
                workflow_name="test-workflow",
                trigger_node_id="nonexistent_trigger",
            )


class TestCreateTemporalExecutionService:
    """Test factory function for creating execution service."""

    @pytest.mark.asyncio
    async def test_create_temporal_execution_service_defaults(self) -> None:
        """Test creating execution service with default parameters."""
        mock_client = Mock()

        with patch("syntara.workflows.workflow_engine.services.temporal_execution_service.Client") as mock_client_class:
            mock_client_class.connect = AsyncMock(return_value=mock_client)

            service = await create_temporal_execution_service()

            assert isinstance(service, TemporalExecutionService)
            assert service.temporal_client is mock_client
            assert service.task_queue == get_settings().task_queue

            mock_client_class.connect.assert_awaited_once_with(
                get_settings().temporal_address,
                namespace=get_settings().temporal_namespace,
                tls=None,
            )

    @pytest.mark.asyncio
    async def test_create_temporal_execution_service_custom_params(self) -> None:
        """Test creating execution service with custom parameters."""
        mock_client = Mock()

        with patch("syntara.workflows.workflow_engine.services.temporal_execution_service.Client") as mock_client_class:
            mock_client_class.connect = AsyncMock(return_value=mock_client)

            service = await create_temporal_execution_service(
                temporal_address="temporal.example.com:7233",
                namespace="production",
                task_queue="prod-queue",
            )

            assert service.task_queue == "prod-queue"

            mock_client_class.connect.assert_awaited_once_with(
                "temporal.example.com:7233",
                namespace="production",
                tls=None,
            )


class TestBuiltinWorkflowRouting:
    """Test queue routing for built-in vs user workflows."""

    def _get_task_queue_from_call(self, mock_client: Mock) -> str:
        call_kwargs = mock_client.start_workflow.call_args
        return str(call_kwargs.kwargs.get("task_queue") or call_kwargs[1].get("task_queue"))

    @pytest.mark.asyncio
    async def test_builtin_workflow_routes_to_background_queue_when_configured(
        self,
        valid_workflow_dict: dict[str, Any],
    ) -> None:
        """is_builtin=True routes to background_task_queue when it is set."""
        mock_client = Mock()
        mock_handle = Mock()
        mock_handle.first_execution_run_id = "run-bg"
        mock_client.start_workflow = AsyncMock(return_value=mock_handle)

        service = TemporalExecutionService(
            temporal_client=mock_client,
            task_queue="orchestrator-workflow-queue",
            background_task_queue="orchestrator-background-queue",
        )

        await service.start_workflow(
            workflow_def=valid_workflow_dict,
            workflow_name="builtin-workflow",
            trigger_node_id="trigger_manual",
            is_builtin=True,
        )

        assert self._get_task_queue_from_call(mock_client) == "orchestrator-background-queue"

    @pytest.mark.asyncio
    async def test_user_workflow_always_routes_to_main_queue(
        self,
        valid_workflow_dict: dict[str, Any],
    ) -> None:
        """is_builtin=False always uses task_queue regardless of background_task_queue."""
        mock_client = Mock()
        mock_handle = Mock()
        mock_handle.first_execution_run_id = "run-user"
        mock_client.start_workflow = AsyncMock(return_value=mock_handle)

        service = TemporalExecutionService(
            temporal_client=mock_client,
            task_queue="orchestrator-workflow-queue",
            background_task_queue="orchestrator-background-queue",
        )

        await service.start_workflow(
            workflow_def=valid_workflow_dict,
            workflow_name="user-workflow",
            trigger_node_id="trigger_manual",
            is_builtin=False,
        )

        assert self._get_task_queue_from_call(mock_client) == "orchestrator-workflow-queue"


class TestWorkflowDataConversion:
    """Test workflow definition data conversion."""

    @pytest.mark.asyncio
    async def test_workflow_def_converted_to_dict(self, valid_workflow_dict: dict[str, Any]) -> None:
        """Test that workflow definition is properly converted to dict for Temporal."""
        mock_client = Mock()
        mock_handle = Mock()
        mock_handle.first_execution_run_id = "run-123"

        # Capture the arguments passed to start_workflow
        captured_args: list[object] = []

        def capture_and_return(*args: object, **kwargs: object) -> Mock:
            """Capture args from start_workflow call."""
            args_list = kwargs.get("args")
            if isinstance(args_list, list):
                captured_args.extend(args_list)
            return mock_handle

        mock_client.start_workflow = AsyncMock(side_effect=capture_and_return)

        service = TemporalExecutionService(temporal_client=mock_client, task_queue="test-queue")

        await service.start_workflow(
            workflow_def=valid_workflow_dict,
            workflow_name="test-workflow",
            trigger_node_id="trigger_manual",
        )

        # Verify first argument is a dict (V2 workflow definition)
        assert len(captured_args) >= 1
        workflow_def_arg = captured_args[0]
        assert isinstance(workflow_def_arg, dict)
        assert "schema_version" in workflow_def_arg
        assert workflow_def_arg["schema_version"] == "2.0.0"
