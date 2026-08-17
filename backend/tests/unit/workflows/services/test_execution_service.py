"""Unit tests for workflow ExecutionService.

These tests verify the business logic layer for execution management.
"""

from datetime import UTC, datetime
from typing import Any, ClassVar
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.core.models.pagination import ResourcesResponseBase
from syntara.metrics.interface_tag import interface_context_var
from syntara.workflows.exceptions import (
    ExecutionNotFoundError,
    TriggerValidationError,
    WorkflowNotFoundError,
    WorkflowNotPublishedError,
)
from syntara.workflows.models.execution import Execution, ExecutionRead, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.execution_service import ExecutionService, count_active_executions
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType


class TestExecutionServiceBase:
    """Base test class with helper methods for ExecutionService tests."""

    def _create_test_execution(  # noqa: C901
        self,
        execution_id: UUID | None = None,
        workflow_id: UUID | None = None,
        workflow_version_id: UUID | None = None,
        temporal_workflow_id: str | None = None,
        status: ExecutionStatus = ExecutionStatus.COMPLETED,
        created_by: UUID | None = None,
        created_at: datetime | None = None,
        updated_at: datetime | None = None,
        updated_by: UUID | None = None,
        completed_at: datetime | None = None,
        input_data: dict[str, Any] | None = None,
        error_details: str | None = None,
        labels: dict[str, Any] | None = None,
        deleted_at: datetime | None = None,
        deleted_by: UUID | None = None,
        project_id: UUID | None = None,
    ) -> Execution:
        """Create a test Execution object with realistic data.

        Args:
            execution_id: Execution UUID (generates random if None)
            workflow_id: Workflow UUID (generates random if None)
            workflow_version_id: Workflow version UUID (generates random if None)
            temporal_workflow_id: Temporal workflow ID (generates if None)
            status: Execution status (defaults to COMPLETED)
            created_by: Creator user UUID (generates random if None)
            created_at: Creation timestamp (defaults to current time if None)
            updated_at: Update timestamp (defaults to created_at if None)
            updated_by: Updater user UUID (defaults to created_by if None)
            completed_at: Completion timestamp (defaults to updated_at for COMPLETED status)
            input_data: Input data dict (defaults to empty dict if None)
            error_details: Error details string (None by default)
            labels: Labels dict (defaults to empty dict if None)
            deleted_at: Deletion timestamp (None by default)
            deleted_by: Deleter user UUID (None by default)
            project_id: Project UUID (generates random if None)

        Returns:
            Execution object with realistic data suitable for testing

        """
        if execution_id is None:
            execution_id = uuid4()
        if workflow_id is None:
            workflow_id = uuid4()
        if workflow_version_id is None:
            workflow_version_id = uuid4()
        if temporal_workflow_id is None:
            temporal_workflow_id = f"temporal-exec-{execution_id}"
        if created_by is None:
            created_by = uuid4()
        if created_at is None:
            created_at = datetime.now(UTC)
        if updated_at is None:
            updated_at = created_at
        if updated_by is None:
            updated_by = created_by
        if completed_at is None and status in (
            ExecutionStatus.COMPLETED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        ):
            completed_at = updated_at
        if input_data is None:
            input_data = {}
        if labels is None:
            labels = {}

        return Execution(
            id=execution_id,
            workflow_id=workflow_id,
            workflow_version_id=workflow_version_id,
            temporal_workflow_id=temporal_workflow_id,
            status=status,
            created_by=created_by,
            created_at=created_at,
            updated_at=updated_at,
            updated_by=updated_by,
            completed_at=completed_at,
            input_data=input_data,
            error_details=error_details,
            labels=labels,
            deleted_at=deleted_at,
            deleted_by=deleted_by,
            project_id=project_id or uuid4(),
        )


class TestExecutionServiceInit:
    """Test ExecutionService initialization."""

    def test_init_with_session_and_user(self) -> None:
        """Test initialization with database session and user."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)
        service = ExecutionService(session=mock_session, user=mock_user)

        assert service.session is mock_session
        assert service.user is mock_user
        assert service.temporal_service is None

    def test_init_with_temporal_service(self) -> None:
        """Test initialization with Temporal service."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)
        mock_temporal = Mock()
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=mock_temporal)

        assert service.session is mock_session
        assert service.user is mock_user
        assert service.temporal_service is mock_temporal


class TestCreateExecution:
    """Test create_execution method."""

    @pytest.mark.asyncio
    async def test_create_execution_success_with_temporal(self) -> None:  # noqa: PLR0915
        """Test successful execution creation with Temporal integration."""
        # Setup mocks
        mock_session = Mock(spec=AsyncSession)
        mock_temporal = Mock()

        workflow_id = uuid4()
        version_id = uuid4()
        user_id = uuid4()

        # Mock workflow and version
        workflow = Mock(spec=Workflow)
        workflow.id = workflow_id
        workflow.name = "test-workflow"
        workflow.is_enabled = True
        workflow.is_builtin = False
        workflow.project_id = uuid4()

        workflow_version = Mock(spec=WorkflowVersion)
        workflow_version.id = version_id
        workflow_version.version = 1
        workflow_version.schema_version = "2.0.0"
        workflow_version.workflow_definition = {
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger_1", "type": NodeType.MANUAL_TRIGGER, "parameters": {}}],
            "nodes": [],
            "edges": [],
        }

        # Mock database query
        mock_result = Mock()
        mock_result.first = Mock(return_value=(workflow, workflow_version))
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Mock Temporal service
        temporal_execution_id = uuid4()
        temporal_result = Mock()
        temporal_result.execution_id = str(temporal_execution_id)
        temporal_result.temporal_workflow_id = "exec-abc123"
        temporal_result.temporal_run_id = "run-xyz789"
        mock_temporal.start_workflow = AsyncMock(return_value=temporal_result)

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=mock_temporal)

        # Execute
        result = await service.create_execution(
            workflow_id=workflow_id,
            input_data={"key": "value"},
            trigger_node_id="trigger_1",
        )

        # Verify
        assert isinstance(result, ExecutionRead)
        assert result.id == temporal_execution_id
        assert result.workflow_id == workflow_id
        assert result.workflow_version_id == version_id
        assert result.temporal_workflow_id == "exec-abc123"
        assert result.status == ExecutionStatus.PENDING
        assert result.input_data == {"key": "value"}
        assert result.created_by == user_id
        assert result.updated_by == user_id

        # Verify Temporal was called
        mock_temporal.start_workflow.assert_awaited_once()
        call_kwargs = mock_temporal.start_workflow.call_args.kwargs
        assert call_kwargs["workflow_name"] == "test-workflow"
        assert call_kwargs["input_data"] == {"key": "value"}
        assert "workflow_def" in call_kwargs
        assert call_kwargs["is_builtin"] is False

        # Verify database operations
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_execution_passes_is_builtin_for_builtin_workflow(self) -> None:
        """Builtin workflows pass is_builtin=True so they route to the background queue."""
        mock_session = Mock(spec=AsyncSession)
        mock_temporal = Mock()

        workflow_id = uuid4()
        version_id = uuid4()
        user_id = uuid4()

        workflow = Mock(spec=Workflow)
        workflow.id = workflow_id
        workflow.name = "Document Conversion"
        workflow.is_enabled = True
        workflow.is_builtin = True
        workflow.project_id = uuid4()

        workflow_version = Mock(spec=WorkflowVersion)
        workflow_version.id = version_id
        workflow_version.version = 1
        workflow_version.schema_version = "2.0.0"
        workflow_version.workflow_definition = {
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger_1", "type": NodeType.MANUAL_TRIGGER, "parameters": {}}],
            "nodes": [],
            "edges": [],
        }

        mock_result = Mock()
        mock_result.first = Mock(return_value=(workflow, workflow_version))
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        temporal_result = Mock()
        temporal_result.execution_id = str(uuid4())
        temporal_result.temporal_workflow_id = "exec-builtin"
        temporal_result.temporal_run_id = "run-builtin"
        mock_temporal.start_workflow = AsyncMock(return_value=temporal_result)

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=mock_temporal)

        await service.create_execution(workflow_id=workflow_id, input_data={}, trigger_node_id="trigger_1")

        call_kwargs = mock_temporal.start_workflow.call_args.kwargs
        assert call_kwargs["is_builtin"] is True

    @pytest.mark.asyncio
    async def test_create_execution_passes_workflow_metadata_with_project_id(self) -> None:
        """workflow_metadata with project_id is passed to Temporal (prevents approval regression)."""
        mock_session = Mock(spec=AsyncSession)
        mock_temporal = Mock()

        workflow = Mock(spec=Workflow)
        workflow.id = uuid4()
        workflow.name = "test-workflow"
        workflow.is_enabled = True
        workflow.project_id = uuid4()

        workflow_version = Mock(spec=WorkflowVersion)
        workflow_version.id = uuid4()
        workflow_version.version = 1
        workflow_version.schema_version = "2.0.0"
        workflow_version.workflow_definition = {
            "schema_version": "2.0.0",
            "triggers": [{"id": "trigger_1", "type": NodeType.MANUAL_TRIGGER, "parameters": {}}],
            "nodes": [],
            "edges": [],
        }

        mock_result = Mock()
        mock_result.first = Mock(return_value=(workflow, workflow_version))
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        temporal_result = Mock()
        temporal_result.execution_id = str(uuid4())
        temporal_result.temporal_workflow_id = "exec-abc"
        temporal_result.temporal_run_id = "run-xyz"
        mock_temporal.start_workflow = AsyncMock(return_value=temporal_result)

        mock_user = Mock(spec=User)
        mock_user.id = uuid4()
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=mock_temporal)

        await service.create_execution(workflow_id=workflow.id, input_data={}, trigger_node_id="trigger_1")

        call_kwargs = mock_temporal.start_workflow.call_args.kwargs
        wf_meta = call_kwargs["workflow_metadata"]
        assert wf_meta is not None
        assert wf_meta["workflow_context"]["workflow"]["project_id"] == str(workflow.project_id)
        assert wf_meta["workflow_context"]["execution"]["mode"] == "standard"

    @pytest.mark.asyncio
    async def test_create_execution_success_without_temporal(self) -> None:
        """Test successful execution creation without Temporal (stub mode)."""
        mock_session = Mock(spec=AsyncSession)

        workflow_id = uuid4()
        version_id = uuid4()
        user_id = uuid4()

        # Mock workflow and version
        workflow = Mock(spec=Workflow)
        workflow.id = workflow_id
        workflow.name = "test-workflow"
        workflow.is_enabled = True
        workflow.project_id = uuid4()

        workflow_version = Mock(spec=WorkflowVersion)
        workflow_version.id = version_id
        workflow_version.version = 1
        workflow_version.schema_version = "2.0.0"
        workflow_version.workflow_definition = {
            "triggers": [{"id": "trigger_1", "type": NodeType.MANUAL_TRIGGER, "parameters": {}}],
        }

        # Mock database query
        mock_result = Mock()
        mock_result.first = Mock(return_value=(workflow, workflow_version))
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)

        # Execute
        result = await service.create_execution(
            workflow_id=workflow_id,
            input_data={},
            trigger_node_id="trigger_1",
        )

        # Verify stub temporal_workflow_id was generated
        assert result.temporal_workflow_id.startswith("exec-")
        UUID(result.temporal_workflow_id.replace("exec-", ""))  # Verify it's a UUID

    @pytest.mark.asyncio
    async def test_create_execution_workflow_not_found(self) -> None:
        """Test execution creation with non-existent workflow."""
        mock_session = Mock(spec=AsyncSession)

        # Mock empty result
        mock_result = Mock()
        mock_result.first = Mock(return_value=None)
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)

        mock_user = Mock(spec=User)
        service = ExecutionService(session=mock_session, user=mock_user)

        workflow_id = uuid4()
        with pytest.raises(WorkflowNotFoundError) as exc_info:
            await service.create_execution(
                workflow_id=workflow_id,
                input_data={},
                trigger_node_id="trigger_1",
            )

        assert str(workflow_id) in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_execution_use_published_success(self) -> None:
        """Test triggered execution uses published version successfully."""
        mock_session = Mock(spec=AsyncSession)

        workflow_id = uuid4()
        version_id = uuid4()
        user_id = uuid4()

        workflow = Mock(spec=Workflow)
        workflow.id = workflow_id
        workflow.name = "test-workflow"
        workflow.is_enabled = True
        workflow.published_version_id = version_id
        workflow.project_id = uuid4()

        workflow_version = Mock(spec=WorkflowVersion)
        workflow_version.id = version_id
        workflow_version.version = 1
        workflow_version.schema_version = "2.0.0"
        workflow_version.workflow_definition = {
            "triggers": [{"id": "trigger_1", "type": NodeType.MANUAL_TRIGGER, "parameters": {}}],
        }

        mock_result = Mock()
        mock_result.first = Mock(return_value=(workflow, workflow_version))
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)

        result = await service.create_execution(
            workflow_id=workflow_id,
            input_data={},
            use_published=True,
            trigger_node_id="trigger_1",
        )

        assert result.temporal_workflow_id.startswith("exec-")
        assert result.workflow_version_id == version_id

    @pytest.mark.asyncio
    async def test_create_execution_use_published_no_published_version(self) -> None:
        """Test triggered execution fails when no published version exists."""
        mock_session = Mock(spec=AsyncSession)
        workflow_id = uuid4()
        mock_result = Mock()
        mock_result.first = Mock(return_value=None)
        workflow = Mock(spec=Workflow)
        workflow.id = workflow_id
        mock_wf_result = Mock()
        mock_wf_result.first = Mock(return_value=workflow)
        mock_session.exec = AsyncMock(side_effect=[mock_result, mock_wf_result])
        mock_session.scalar = AsyncMock(return_value=0)
        mock_user = Mock(spec=User)
        service = ExecutionService(session=mock_session, user=mock_user)
        with pytest.raises(WorkflowNotPublishedError) as exc_info:
            await service.create_execution(
                workflow_id=workflow_id,
                input_data={},
                use_published=True,
                trigger_node_id="trigger_1",
            )
        assert str(workflow_id) in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_execution_cancels_temporal_on_db_failure(self) -> None:
        """Test that Temporal workflow is cancelled when DB commit fails."""
        mock_session = Mock(spec=AsyncSession)
        mock_temporal = Mock()

        workflow_id = uuid4()
        version_id = uuid4()
        user_id = uuid4()

        workflow = Mock(spec=Workflow)
        workflow.id = workflow_id
        workflow.name = "test-workflow"
        workflow.current_version = 1
        workflow.published_version = None
        workflow.project_id = uuid4()
        workflow.created_by = user_id
        workflow.deleted_at = None

        version = Mock(spec=WorkflowVersion)
        version.id = version_id
        version.version = 1
        version.workflow_definition = {
            "triggers": [{"id": "t1", "type": "manual_trigger", "parameters": {}}],
            "nodes": [],
            "edges": [],
        }

        mock_result = Mock()
        mock_result.first = Mock(return_value=(workflow, version))
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock(side_effect=Exception("DB commit failed"))

        temporal_result = Mock()
        temporal_result.temporal_workflow_id = f"temporal-{uuid4()}"
        temporal_result.execution_id = str(uuid4())
        temporal_result.temporal_run_id = f"run-{uuid4()}"
        mock_temporal.start_workflow = AsyncMock(return_value=temporal_result)
        mock_temporal.cancel_workflow = AsyncMock()

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        mock_user.display_name = "Test User"

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=mock_temporal,
        )

        with (
            patch(
                "syntara.workflows.services.execution_service.resolve_user_display_name",
                new_callable=AsyncMock,
                return_value="Author",
            ),
            pytest.raises(Exception, match="DB commit failed"),
        ):
            await service.create_execution(workflow_id=workflow_id, input_data={}, trigger_node_id="t1")

        mock_temporal.cancel_workflow.assert_awaited_once_with(
            temporal_workflow_id=temporal_result.temporal_workflow_id
        )

    @pytest.mark.asyncio
    async def test_create_execution_sets_trigger_type_from_resolved_trigger_node(self) -> None:
        """Test that trigger_type is set from the resolved trigger node's type field."""
        mock_session = Mock(spec=AsyncSession)

        workflow_id = uuid4()
        version_id = uuid4()
        user_id = uuid4()

        workflow = Mock(spec=Workflow)
        workflow.id = workflow_id
        workflow.name = "test-workflow"
        workflow.is_enabled = True
        workflow.project_id = uuid4()

        workflow_version = Mock(spec=WorkflowVersion)
        workflow_version.id = version_id
        workflow_version.version = 1
        workflow_version.schema_version = "2.0.0"
        workflow_version.workflow_definition = {
            "triggers": [{"id": "trigger_1", "type": NodeType.WEBHOOK_TRIGGER, "parameters": {}}],
        }

        mock_result = Mock()
        mock_result.first = Mock(return_value=(workflow, workflow_version))
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)

        result = await service.create_execution(
            workflow_id=workflow_id,
            input_data={},
            trigger_node_id="trigger_1",
        )

        # Verify the Execution object stored in the database
        execution = mock_session.add.call_args[0][0]
        assert execution.trigger_type == NodeType.WEBHOOK_TRIGGER

        # Verify it propagates to the returned ExecutionRead
        assert result.trigger_type == NodeType.WEBHOOK_TRIGGER

    @pytest.mark.asyncio
    async def test_create_execution_sets_trigger_type_for_manual_trigger(self) -> None:
        """Test that trigger_type is set to manual_trigger when using default trigger resolution."""
        mock_session = Mock(spec=AsyncSession)

        workflow_id = uuid4()
        version_id = uuid4()
        user_id = uuid4()

        workflow = Mock(spec=Workflow)
        workflow.id = workflow_id
        workflow.name = "test-workflow"
        workflow.is_enabled = True
        workflow.project_id = uuid4()

        workflow_version = Mock(spec=WorkflowVersion)
        workflow_version.id = version_id
        workflow_version.version = 1
        workflow_version.schema_version = "2.0.0"
        workflow_version.workflow_definition = {
            "triggers": [{"id": "trigger_1", "type": NodeType.MANUAL_TRIGGER, "parameters": {}}],
        }

        mock_result = Mock()
        mock_result.first = Mock(return_value=(workflow, workflow_version))
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)

        result = await service.create_execution(
            workflow_id=workflow_id,
            input_data={},
            trigger_node_id="trigger_1",
        )

        # Verify the Execution object stored in the database
        execution = mock_session.add.call_args[0][0]
        assert execution.trigger_type == NodeType.MANUAL_TRIGGER

        # Verify it propagates to the returned ExecutionRead
        assert result.trigger_type == NodeType.MANUAL_TRIGGER

    @pytest.mark.asyncio
    async def test_create_execution_sets_interface_from_context_var(self) -> None:
        """Test that interface is set from interface_context_var."""
        mock_session = Mock(spec=AsyncSession)

        workflow_id = uuid4()
        version_id = uuid4()
        user_id = uuid4()

        workflow = Mock(spec=Workflow)
        workflow.id = workflow_id
        workflow.name = "test-workflow"
        workflow.is_enabled = True
        workflow.project_id = uuid4()

        workflow_version = Mock(spec=WorkflowVersion)
        workflow_version.id = version_id
        workflow_version.version = 1
        workflow_version.schema_version = "2.0.0"
        workflow_version.workflow_definition = {
            "triggers": [{"id": "trigger_1", "type": NodeType.MANUAL_TRIGGER, "parameters": {}}],
        }

        mock_result = Mock()
        mock_result.first = Mock(return_value=(workflow, workflow_version))
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)

        # Set the interface context var to "ui" and verify it propagates
        token = interface_context_var.set("ui")
        try:
            result = await service.create_execution(
                workflow_id=workflow_id,
                input_data={},
                trigger_node_id="trigger_1",
            )

            # Verify the Execution object stored in the database
            execution = mock_session.add.call_args[0][0]
            assert execution.interface == "ui"

            # Verify it propagates to the returned ExecutionRead
            assert result.interface == "ui"
        finally:
            interface_context_var.reset(token)

    @pytest.mark.asyncio
    async def test_create_execution_sets_interface_default_api(self) -> None:
        """Test that interface defaults to 'api' when context var is not explicitly set."""
        mock_session = Mock(spec=AsyncSession)

        workflow_id = uuid4()
        version_id = uuid4()
        user_id = uuid4()

        workflow = Mock(spec=Workflow)
        workflow.id = workflow_id
        workflow.name = "test-workflow"
        workflow.is_enabled = True
        workflow.project_id = uuid4()

        workflow_version = Mock(spec=WorkflowVersion)
        workflow_version.id = version_id
        workflow_version.version = 1
        workflow_version.schema_version = "2.0.0"
        workflow_version.workflow_definition = {
            "triggers": [{"id": "trigger_1", "type": NodeType.MANUAL_TRIGGER, "parameters": {}}],
        }

        mock_result = Mock()
        mock_result.first = Mock(return_value=(workflow, workflow_version))
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)
        mock_session.add = Mock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        mock_user = Mock(spec=User)
        mock_user.id = user_id
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)

        result = await service.create_execution(
            workflow_id=workflow_id,
            input_data={},
            trigger_node_id="trigger_1",
        )

        # Verify the Execution object stored in the database
        execution = mock_session.add.call_args[0][0]
        assert execution.interface == "api"

        # Verify it propagates to the returned ExecutionRead
        assert result.interface == "api"


class TestConcurrencyCheck:
    """Unit tests for count_active_executions and the concurrency gate."""

    @pytest.mark.asyncio
    async def test_count_active_executions_returns_db_value(self) -> None:
        """count_active_executions returns whatever the DB scalar returns."""
        mock_session = Mock(spec=AsyncSession)
        mock_session.scalar = AsyncMock(return_value=7)

        result = await count_active_executions(mock_session)

        assert result == 7
        mock_session.scalar.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_active_executions_coerces_none_to_zero(self) -> None:
        """count_active_executions returns 0 when DB returns None (empty table)."""
        mock_session = Mock(spec=AsyncSession)
        mock_session.scalar = AsyncMock(return_value=None)

        result = await count_active_executions(mock_session)

        assert result == 0

    @pytest.mark.asyncio
    async def test_gate_raises_when_active_meets_limit(self) -> None:
        """_start_temporal_and_create_execution raises WorkflowConcurrencyLimitError when active >= limit."""
        from syntara.workflows.exceptions import WorkflowConcurrencyLimitError

        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)
        mock_user.id = uuid4()
        service = ExecutionService(session=mock_session, user=mock_user)

        workflow = Mock(spec=Workflow)
        workflow_version = Mock(spec=WorkflowVersion)
        recorder = Mock()
        component = Mock()

        with (
            patch("syntara.workflows.services.execution_service.get_settings") as mock_get_settings,
            patch(
                "syntara.workflows.services.execution_service.count_active_executions",
                new_callable=AsyncMock,
                return_value=5,
            ) as mock_count,
        ):
            mock_get_settings.return_value.max_concurrent_workflows = 5

            with pytest.raises(WorkflowConcurrencyLimitError) as exc_info:
                await service._start_temporal_and_create_execution(
                    workflow=workflow,
                    workflow_version=workflow_version,
                    input_data={},
                    trigger_node_id="t1",
                    recorder=recorder,
                    component=component,
                )

        mock_count.assert_awaited_once_with(mock_session)
        assert exc_info.value.limit == 5
        assert exc_info.value.active == 5

    @pytest.mark.asyncio
    async def test_gate_allows_when_under_limit(self) -> None:
        """_start_temporal_and_create_execution proceeds past the gate when active < limit."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)
        mock_user.id = uuid4()
        service = ExecutionService(session=mock_session, user=mock_user)

        workflow = Mock(spec=Workflow)
        workflow_version = Mock(spec=WorkflowVersion)
        recorder = Mock()
        component = Mock()

        with (
            patch("syntara.workflows.services.execution_service.get_settings") as mock_get_settings,
            patch(
                "syntara.workflows.services.execution_service.count_active_executions",
                new_callable=AsyncMock,
                return_value=2,
            ) as mock_count,
            patch(
                "syntara.workflows.services.execution_service.resolve_user_display_name",
                new_callable=AsyncMock,
                side_effect=RuntimeError("sentinel"),
            ),
        ):
            mock_get_settings.return_value.max_concurrent_workflows = 5

            with pytest.raises(RuntimeError, match="sentinel"):
                await service._start_temporal_and_create_execution(
                    workflow=workflow,
                    workflow_version=workflow_version,
                    input_data={},
                    trigger_node_id="t1",
                    recorder=recorder,
                    component=component,
                )

        mock_count.assert_awaited_once_with(mock_session)

    @pytest.mark.asyncio
    async def test_limit_zero_skips_check(self) -> None:
        """When max_concurrent_workflows=0, count_active_executions is never called."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)
        mock_user.id = uuid4()
        service = ExecutionService(session=mock_session, user=mock_user)

        workflow = Mock(spec=Workflow)
        workflow_version = Mock(spec=WorkflowVersion)
        recorder = Mock()
        component = Mock()

        with (
            patch("syntara.workflows.services.execution_service.get_settings") as mock_get_settings,
            patch(
                "syntara.workflows.services.execution_service.count_active_executions",
                new_callable=AsyncMock,
            ) as mock_count,
            patch(
                "syntara.workflows.services.execution_service.resolve_user_display_name",
                new_callable=AsyncMock,
                side_effect=RuntimeError("sentinel"),
            ),
        ):
            mock_get_settings.return_value.max_concurrent_workflows = 0

            with pytest.raises(RuntimeError, match="sentinel"):
                await service._start_temporal_and_create_execution(
                    workflow=workflow,
                    workflow_version=workflow_version,
                    input_data={},
                    trigger_node_id="t1",
                    recorder=recorder,
                    component=component,
                )

        mock_count.assert_not_called()


class TestCreateExecutionByName:
    """Test create_execution_by_name method."""

    @pytest.mark.asyncio
    async def test_create_execution_by_name_resolves_trigger(self) -> None:
        """Test that create_execution_by_name extracts trigger_node_id from the published definition."""
        mock_session = Mock(spec=AsyncSession)

        workflow = Mock(spec=Workflow)
        workflow.id = uuid4()
        workflow.name = "Document Conversion"
        workflow.is_enabled = True
        workflow.project_id = uuid4()

        workflow_version = Mock(spec=WorkflowVersion)
        workflow_version.id = uuid4()
        workflow_version.version = 1
        workflow_version.schema_version = "2.0.0"
        workflow_version.workflow_definition = {
            "triggers": [{"id": "builtin_trigger", "type": "manual_trigger", "parameters": {}}],
            "nodes": [],
            "edges": [],
        }

        mock_result = Mock()
        mock_result.first = Mock(return_value=(workflow, workflow_version))
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)

        mock_user = Mock(spec=User)
        mock_user.id = uuid4()
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)

        with patch.object(service, "create_execution", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = Mock(spec=ExecutionRead)
            await service.create_execution_by_name(
                workflow_name="Document Conversion",
                input_data={"file_id": "abc"},
                project_name="Builtin",
            )

            mock_create.assert_called_once_with(
                workflow_id=workflow.id,
                input_data={"file_id": "abc"},
                trigger_node_id="builtin_trigger",
                use_published=True,
            )

    @pytest.mark.asyncio
    async def test_create_execution_by_name_raises_when_not_found(self) -> None:
        """Test that create_execution_by_name raises WorkflowNotFoundError."""
        mock_session = Mock(spec=AsyncSession)
        mock_result = Mock()
        mock_result.first = Mock(return_value=None)
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)

        mock_user = Mock(spec=User)
        mock_user.id = uuid4()
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)

        with pytest.raises(WorkflowNotFoundError):
            await service.create_execution_by_name(
                workflow_name="Nonexistent",
                input_data={},
                project_name="Builtin",
            )

    @pytest.mark.asyncio
    async def test_create_execution_by_name_raises_when_no_triggers(self) -> None:
        """Test that create_execution_by_name raises when workflow has no triggers."""
        mock_session = Mock(spec=AsyncSession)

        workflow = Mock(spec=Workflow)
        workflow.id = uuid4()

        workflow_version = Mock(spec=WorkflowVersion)
        workflow_version.workflow_definition = {"triggers": [], "nodes": [], "edges": []}

        mock_result = Mock()
        mock_result.first = Mock(return_value=(workflow, workflow_version))
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)

        mock_user = Mock(spec=User)
        mock_user.id = uuid4()
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)

        with pytest.raises(SafeValueError, match="has no triggers"):
            await service.create_execution_by_name(
                workflow_name="Bad Workflow",
                input_data={},
                project_name="Builtin",
            )


class TestRetryExecutionTriggerNodeId:
    """Test retry_execution trigger_node_id validation."""

    @pytest.mark.asyncio
    async def test_retry_raises_when_original_has_no_trigger_node_id(self) -> None:
        """Test that retrying an execution without trigger_node_id raises SafeValueError."""
        mock_session = Mock(spec=AsyncSession)

        workflow = Mock(spec=Workflow)
        workflow.id = uuid4()
        workflow.deleted_at = None

        original = Mock(spec=Execution)
        original.id = uuid4()
        original.workflow_id = workflow.id
        original.workflow_version_id = uuid4()
        original.trigger_node_id = None
        original.status = ExecutionStatus.FAILED
        original.mode = "standard"
        original.retried_from_execution_id = None
        original.workflow = workflow

        workflow_version = Mock(spec=WorkflowVersion)
        workflow_version.id = original.workflow_version_id
        workflow_version.deleted_at = None
        workflow_version.workflow_definition = {
            "triggers": [{"id": "t1", "type": "manual_trigger"}],
        }

        mock_exec_result = Mock()
        mock_exec_result.one_or_none = Mock(return_value=original)
        mock_version_result = Mock()
        mock_version_result.one_or_none = Mock(return_value=workflow_version)
        mock_session.exec = AsyncMock(side_effect=[mock_exec_result, mock_version_result])
        mock_session.scalar = AsyncMock(return_value=0)

        mock_user = Mock(spec=User)
        mock_user.id = uuid4()
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)

        with pytest.raises(SafeValueError, match="no trigger_node_id recorded"):
            await service.retry_execution(execution_id=original.id)


class TestGetExecution(TestExecutionServiceBase):
    """Test get_execution method."""

    @pytest.mark.asyncio
    async def test_get_execution_success_without_temporal(self) -> None:
        """Test successfully retrieving an execution without Temporal sync."""
        mock_session = Mock(spec=AsyncSession)

        execution_id = uuid4()
        execution = self._create_test_execution(execution_id=execution_id)

        mock_result = Mock()
        mock_result.one_or_none = Mock(return_value=execution)
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)

        mock_user = Mock(spec=User)
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)

        with patch.object(service, "_emit_completion_metrics", new_callable=AsyncMock):
            result = await service.get_execution(execution_id)

        assert isinstance(result, ExecutionRead)
        assert result.id == execution_id

    @pytest.mark.asyncio
    async def test_get_execution_success_returns_database_status(self) -> None:
        """Test retrieving execution returns status directly from database."""
        mock_session = Mock(spec=AsyncSession)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        execution_id = uuid4()
        execution = self._create_test_execution(
            execution_id=execution_id,
            status=ExecutionStatus.RUNNING,
            temporal_workflow_id="exec-123",
        )

        mock_result = Mock()
        mock_result.one_or_none = Mock(return_value=execution)
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)

        # Mock Temporal service
        mock_temporal = Mock()

        mock_user = Mock(spec=User)
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=mock_temporal)

        result = await service.get_execution(execution_id)

        assert isinstance(result, ExecutionRead)
        assert result.id == execution_id
        assert result.status == ExecutionStatus.RUNNING
        # Status comes from the database; no commit expected.
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_execution_not_found(self) -> None:
        """Test getting non-existent execution."""
        mock_session = Mock(spec=AsyncSession)

        mock_result = Mock()
        mock_result.one_or_none = Mock(return_value=None)
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)

        mock_user = Mock(spec=User)
        service = ExecutionService(session=mock_session, user=mock_user)

        execution_id = uuid4()
        with pytest.raises(ExecutionNotFoundError) as exc_info:
            await service.get_execution(execution_id)

        assert str(execution_id) in str(exc_info.value)


class TestListExecutions(TestExecutionServiceBase):
    """Test list_executions method."""

    @pytest.mark.asyncio
    async def test_list_executions_basic(self) -> None:
        """Test basic listing without filters."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        # Create real Execution objects using helper method
        exec1_id = uuid4()
        exec2_id = uuid4()

        exec1 = self._create_test_execution(
            execution_id=exec1_id,
            status=ExecutionStatus.COMPLETED,
            created_at=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC),
        )

        exec2 = self._create_test_execution(
            execution_id=exec2_id,
            status=ExecutionStatus.RUNNING,
            created_at=datetime(2025, 1, 1, 11, 0, 0, tzinfo=UTC),
        )

        # Mock database result for main query (exec)
        mock_main_result = Mock()
        mock_main_result.all.return_value = [exec1, exec2]
        mock_session.exec = AsyncMock(return_value=mock_main_result)
        mock_session.scalar = AsyncMock(return_value=0)

        service = ExecutionService(session=mock_session, user=mock_user)
        result = await service.list_executions(limit=10)

        assert isinstance(result, ResourcesResponseBase)
        assert len(result.resources) == 2
        # Now we expect ExecutionRead objects, not the original Execution objects
        assert isinstance(result.resources[0], ExecutionRead)
        assert isinstance(result.resources[1], ExecutionRead)
        # Check the IDs to verify the conversion worked correctly
        assert result.resources[0].id == exec1_id
        assert result.resources[1].id == exec2_id
        assert result.next is None
        assert result.prev is None
        assert result.total is None

    @pytest.mark.asyncio
    async def test_list_executions_with_workflow_filter(self) -> None:
        """Test listing with workflow_id filter."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        workflow_id = uuid4()
        exec1_id = uuid4()
        exec1 = self._create_test_execution(execution_id=exec1_id, workflow_id=workflow_id)

        # Mock database result for main query (exec)
        mock_main_result = Mock()
        mock_main_result.all.return_value = [exec1]
        mock_session.exec = AsyncMock(return_value=mock_main_result)
        mock_session.scalar = AsyncMock(return_value=0)

        service = ExecutionService(session=mock_session, user=mock_user)
        result = await service.list_executions(query_params_items=[("workflow_id", str(workflow_id))], limit=10)

        assert isinstance(result, ResourcesResponseBase)
        assert len(result.resources) == 1
        assert isinstance(result.resources[0], ExecutionRead)
        assert result.resources[0].workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_list_executions_with_status_filter(self) -> None:
        """Test listing with status filter."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        exec1_id = uuid4()
        exec1 = self._create_test_execution(execution_id=exec1_id, status=ExecutionStatus.RUNNING)

        # Mock database result for main query (exec)
        mock_main_result = Mock()
        mock_main_result.all.return_value = [exec1]
        mock_session.exec = AsyncMock(return_value=mock_main_result)
        mock_session.scalar = AsyncMock(return_value=0)

        service = ExecutionService(session=mock_session, user=mock_user)
        result = await service.list_executions(query_params_items=[("status", ExecutionStatus.RUNNING.value)], limit=10)

        assert isinstance(result, ResourcesResponseBase)
        assert len(result.resources) == 1
        assert isinstance(result.resources[0], ExecutionRead)
        assert result.resources[0].status == ExecutionStatus.RUNNING

    @pytest.mark.asyncio
    async def test_list_executions_with_created_by_filter(self) -> None:
        """Test listing with created_by filter."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        user_id = uuid4()
        exec1_id = uuid4()
        exec1 = self._create_test_execution(execution_id=exec1_id, created_by=user_id)

        # Mock database result for main query (exec)
        mock_main_result = Mock()
        mock_main_result.all.return_value = [exec1]
        mock_session.exec = AsyncMock(return_value=mock_main_result)
        mock_session.scalar = AsyncMock(return_value=0)

        service = ExecutionService(session=mock_session, user=mock_user)
        result = await service.list_executions(query_params_items=[("created_by", str(user_id))], limit=10)

        assert isinstance(result, ResourcesResponseBase)
        assert len(result.resources) == 1
        assert isinstance(result.resources[0], ExecutionRead)
        assert result.resources[0].created_by == user_id

    @pytest.mark.asyncio
    async def test_list_executions_with_labels_filter(self) -> None:
        """Test listing with labels filter."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        exec1_id = uuid4()
        exec1 = self._create_test_execution(execution_id=exec1_id, labels={"env": "prod"})

        # Mock database result for main query (exec)
        mock_main_result = Mock()
        mock_main_result.all.return_value = [exec1]
        mock_session.exec = AsyncMock(return_value=mock_main_result)
        mock_session.scalar = AsyncMock(return_value=0)

        service = ExecutionService(session=mock_session, user=mock_user)
        # Using cast to avoid mypy issues with dynamic keyword arguments
        result = await service.list_executions(query_params_items=[("labels[env]", "prod")], limit=10)

        assert isinstance(result, ResourcesResponseBase)
        assert len(result.resources) == 1
        assert isinstance(result.resources[0], ExecutionRead)

    @pytest.mark.asyncio
    async def test_list_executions_with_multiple_filters(self) -> None:
        """Test listing with various filters combined."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        workflow_id = uuid4()
        user_id = uuid4()
        exec1_id = uuid4()
        exec1 = self._create_test_execution(execution_id=exec1_id, workflow_id=workflow_id, created_by=user_id)

        # Mock database result for main query (exec)
        mock_main_result = Mock()
        mock_main_result.all.return_value = [exec1]
        mock_session.exec = AsyncMock(return_value=mock_main_result)
        mock_session.scalar = AsyncMock(return_value=0)

        service = ExecutionService(session=mock_session, user=mock_user)
        result = await service.list_executions(
            query_params_items=[("workflow_id", str(workflow_id)), ("created_by", str(user_id)), ("status", "running")],
            limit=10,
        )

        assert isinstance(result, ResourcesResponseBase)
        assert len(result.resources) == 1
        assert isinstance(result.resources[0], ExecutionRead)
        assert result.resources[0].workflow_id == workflow_id

    @pytest.mark.asyncio
    async def test_list_executions_with_pagination(self) -> None:
        """Test listing with pagination parameters."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        # Create mock execution with proper attributes for pagination
        exec_id = uuid4()
        exec1 = self._create_test_execution(
            execution_id=exec_id, created_at=datetime.fromisoformat("2025-01-01T10:00:00+00:00").replace(tzinfo=UTC)
        )

        # Mock database result for main query (exec)
        mock_main_result = Mock()
        mock_main_result.all.return_value = [exec1]
        mock_session.exec = AsyncMock(return_value=mock_main_result)
        mock_session.scalar = AsyncMock(return_value=0)

        service = ExecutionService(session=mock_session, user=mock_user)
        result = await service.list_executions(limit=5, sort="-created_at")

        assert isinstance(result, ResourcesResponseBase)
        assert len(result.resources) == 1
        assert isinstance(result.resources[0], ExecutionRead)
        # Note: next/prev cursors are generated by the pagination utility based on the results

    @pytest.mark.asyncio
    async def test_list_executions_with_total_count(self) -> None:
        """Test listing with total count included."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        exec1_id = uuid4()
        exec1 = self._create_test_execution(execution_id=exec1_id)

        # Mock database result for main query (exec)
        mock_main_result = Mock()
        mock_main_result.all.return_value = [exec1]

        # Mock database result for count query (exec)
        mock_count_result = Mock()
        mock_count_result.one.return_value = 42

        # Setup exec to return different results based on call order
        mock_session.exec = AsyncMock(side_effect=[mock_main_result, mock_count_result])
        mock_session.scalar = AsyncMock(return_value=0)

        service = ExecutionService(session=mock_session, user=mock_user)
        result = await service.list_executions(include_total=True)

        assert isinstance(result, ResourcesResponseBase)
        assert len(result.resources) == 1
        assert isinstance(result.resources[0], ExecutionRead)
        assert result.total == 42

    @pytest.mark.asyncio
    async def test_list_executions_with_label_filters(self) -> None:
        """Test listing with label filters using bracket notation."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        exec1_id = uuid4()
        exec1 = self._create_test_execution(execution_id=exec1_id, labels={"env": "prod"})

        # Mock database result for main query (exec)
        mock_main_result = Mock()
        mock_main_result.all.return_value = [exec1]
        mock_session.exec = AsyncMock(return_value=mock_main_result)
        mock_session.scalar = AsyncMock(return_value=0)

        service = ExecutionService(session=mock_session, user=mock_user)
        # Test with bracket notation label filter
        result = await service.list_executions(query_params_items=[("labels[env]", "prod")])

        assert isinstance(result, ResourcesResponseBase)
        assert len(result.resources) == 1
        assert isinstance(result.resources[0], ExecutionRead)

    @pytest.mark.asyncio
    async def test_list_executions_empty_result(self) -> None:
        """Test listing when no executions match."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        # Mock database result for main query (exec) - empty
        mock_main_result = Mock()
        mock_main_result.all.return_value = []
        mock_session.exec = AsyncMock(return_value=mock_main_result)
        mock_session.scalar = AsyncMock(return_value=0)

        service = ExecutionService(session=mock_session, user=mock_user)
        result = await service.list_executions(limit=10)

        assert isinstance(result, ResourcesResponseBase)
        assert len(result.resources) == 0
        assert result.resources == []

    @pytest.mark.asyncio
    async def test_list_executions_respects_allowed_filters(self) -> None:
        """Test that only allowed filter fields are processed."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        exec1_id = uuid4()
        exec1 = self._create_test_execution(execution_id=exec1_id)

        # Mock database result for main query (exec)
        mock_main_result = Mock()
        mock_main_result.all.return_value = [exec1]
        mock_session.exec = AsyncMock(return_value=mock_main_result)
        mock_session.scalar = AsyncMock(return_value=0)

        service = ExecutionService(session=mock_session, user=mock_user)

        # Test that valid filters work correctly
        result = await service.list_executions(query_params_items=[("workflow_id[eq]", str(exec1.id))], limit=10)

        assert isinstance(result, ResourcesResponseBase)
        assert len(result.resources) == 1

    @pytest.mark.asyncio
    async def test_list_executions_respects_allowed_sort_fields(self) -> None:
        """Test that only allowed sort fields are processed."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        exec1_id = uuid4()
        exec1 = self._create_test_execution(execution_id=exec1_id)

        # Mock database result for main query (exec)
        mock_main_result = Mock()
        mock_main_result.all.return_value = [exec1]
        mock_session.exec = AsyncMock(return_value=mock_main_result)
        mock_session.scalar = AsyncMock(return_value=0)

        service = ExecutionService(session=mock_session, user=mock_user)

        # Test with valid sort field
        result = await service.list_executions(sort="created_at")
        assert isinstance(result, ResourcesResponseBase)

        # Test with invalid sort field - should raise SafeValueError
        with pytest.raises(SafeValueError, match="Invalid field: invalid_field"):
            await service.list_executions(sort="invalid_field")


class TestListExecutionsWithTemporalSync(TestExecutionServiceBase):
    """Test list_executions_cursor with Temporal synchronization."""

    @pytest.mark.asyncio
    async def test_list_returns_database_status_without_temporal_sync(self) -> None:
        """Test listing executions returns status directly from database without Temporal sync."""
        mock_session = Mock(spec=AsyncSession)
        mock_session.commit = AsyncMock()

        # Create real execution objects with database status
        exec1_id = uuid4()
        exec2_id = uuid4()
        exec1 = self._create_test_execution(
            execution_id=exec1_id, status=ExecutionStatus.RUNNING, temporal_workflow_id="exec-1"
        )
        exec2 = self._create_test_execution(
            execution_id=exec2_id, status=ExecutionStatus.PENDING, temporal_workflow_id="exec-2"
        )

        # Mock database result for main query (exec)
        mock_main_result = Mock()
        mock_main_result.all = Mock(return_value=[exec1, exec2])
        mock_session.exec = AsyncMock(return_value=mock_main_result)
        mock_session.scalar = AsyncMock(return_value=0)

        # Mock Temporal service
        mock_temporal = Mock()

        mock_user = Mock(spec=User)
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=mock_temporal)

        result = await service.list_executions(limit=10)

        assert len(result.resources) == 2
        # Status comes from the database; no commit expected (no status changes to persist).
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_skips_commit_when_no_status_changes(self) -> None:
        """Test listing doesn't commit when no status changes occur."""
        mock_session = Mock(spec=AsyncSession)
        mock_session.commit = AsyncMock()

        # Create real execution object in terminal state
        exec1_id = uuid4()
        exec1 = self._create_test_execution(
            execution_id=exec1_id, status=ExecutionStatus.COMPLETED, temporal_workflow_id="exec-1"
        )

        # Mock database result for main query (exec)
        mock_main_result = Mock()
        mock_main_result.all = Mock(return_value=[exec1])
        mock_session.exec = AsyncMock(return_value=mock_main_result)
        mock_session.scalar = AsyncMock(return_value=0)

        mock_temporal = Mock()

        mock_user = Mock(spec=User)
        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=mock_temporal)

        result = await service.list_executions(limit=10)

        assert len(result.resources) == 1
        # Status comes from the database; no commit expected when no changes.
        mock_session.commit.assert_not_called()


class TestListExecutionActivities(TestExecutionServiceBase):
    """Test list_execution_activities method."""

    @pytest.mark.asyncio
    async def test_list_execution_activities_not_found(self) -> None:
        """Test listing activities for non-existent execution raises error."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        execution_id = uuid4()

        # Mock execution not found
        mock_result = Mock()
        mock_result.one_or_none = Mock(return_value=None)
        mock_session.exec = AsyncMock(return_value=mock_result)
        mock_session.scalar = AsyncMock(return_value=0)

        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)

        with pytest.raises(ExecutionNotFoundError) as exc_info:
            await service.list_execution_activities(execution_id)

        assert exc_info.value.execution_id == execution_id

    @pytest.mark.asyncio
    async def test_list_execution_activities_delegates_to_list_resources(self) -> None:
        """Test that list_execution_activities delegates to list_resources after verifying execution."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        execution_id = uuid4()
        execution = self._create_test_execution(execution_id=execution_id)

        # Mock execution exists check
        mock_execution_result = Mock()
        mock_execution_result.one_or_none = Mock(return_value=execution)
        mock_session.exec = AsyncMock(return_value=mock_execution_result)

        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)

        mock_response = Mock()
        with patch.object(service, "list_resources", new_callable=AsyncMock, return_value=mock_response) as mock_lr:
            result = await service.list_execution_activities(
                execution_id=execution_id,
                limit=10,
                sort="-created_at",
            )

        assert result is mock_response
        mock_lr.assert_awaited_once()
        call_kwargs = mock_lr.call_args.kwargs
        assert call_kwargs["limit"] == 10
        assert call_kwargs["sort"] == "-created_at"

    @pytest.mark.asyncio
    async def test_list_execution_activities_field_mapping(self) -> None:
        """Test that activity field mapping returns correct values for activity_name, status, and retry_count."""
        from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus

        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        execution_id = uuid4()
        execution = self._create_test_execution(execution_id=execution_id)

        # Create a real ActivityExecution with specific field values
        activity_id = uuid4()
        activity = ActivityExecution(
            id=activity_id,
            execution_id=execution_id,
            activity_name="run-script-1",
            node_type="script",
            temporal_activity_id="run-script-1",
            status=ActivityStatus.COMPLETED,
            started_at=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2025, 1, 1, 10, 1, 0, tzinfo=UTC),
            input_data={"host": "server-1"},
            output_data={"stdout": "ok"},
            error_details=None,
            retry_count=2,
            created_at=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 10, 1, 0, tzinfo=UTC),
        )

        # First call: execution exists check
        mock_execution_result = Mock()
        mock_execution_result.one_or_none = Mock(return_value=execution)

        # Second call: list_resources query returns activities
        mock_activities_result = Mock()
        mock_activities_result.all = Mock(return_value=[activity])

        mock_session.exec = AsyncMock(side_effect=[mock_execution_result, mock_activities_result])

        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)
        result = await service.list_execution_activities(execution_id=execution_id, limit=10)

        assert len(result.resources) == 1
        returned_activity = result.resources[0]
        assert returned_activity.activity_name == "run-script-1"
        assert returned_activity.status == ActivityStatus.COMPLETED
        assert returned_activity.retry_count == 2
        assert returned_activity.output_data == {"stdout": "ok"}
        assert returned_activity.input_data == {"host": "server-1"}
        assert returned_activity.started_at == datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        assert returned_activity.completed_at == datetime(2025, 1, 1, 10, 1, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_list_execution_activities_empty_list(self) -> None:
        """Test that empty activity list returns empty resources."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        execution_id = uuid4()
        execution = self._create_test_execution(execution_id=execution_id)

        # First call: execution exists check
        mock_execution_result = Mock()
        mock_execution_result.one_or_none = Mock(return_value=execution)

        # Second call: no activities found
        mock_activities_result = Mock()
        mock_activities_result.all = Mock(return_value=[])

        mock_session.exec = AsyncMock(side_effect=[mock_execution_result, mock_activities_result])

        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)
        result = await service.list_execution_activities(execution_id=execution_id, limit=10)

        assert len(result.resources) == 0
        assert result.resources == []

    @pytest.mark.asyncio
    async def test_list_execution_activities_multiple_activities(self) -> None:
        """Test that multiple activities are returned correctly with proper field values."""
        from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus

        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        execution_id = uuid4()
        execution = self._create_test_execution(execution_id=execution_id)

        # Create multiple activities with different statuses and field values
        activity1 = ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="step-1-script",
            node_type="script",
            temporal_activity_id="step-1-script",
            status=ActivityStatus.COMPLETED,
            started_at=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC),
            completed_at=datetime(2025, 1, 1, 10, 1, 0, tzinfo=UTC),
            input_data={"cmd": "echo hello"},
            output_data={"stdout": "hello"},
            error_details=None,
            retry_count=0,
            created_at=datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 10, 1, 0, tzinfo=UTC),
        )
        activity2 = ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="step-2-http",
            node_type="http_request",
            temporal_activity_id="step-2-http",
            status=ActivityStatus.FAILED,
            started_at=datetime(2025, 1, 1, 10, 2, 0, tzinfo=UTC),
            completed_at=datetime(2025, 1, 1, 10, 3, 0, tzinfo=UTC),
            input_data={"url": "https://example.com"},
            output_data=None,
            error_details="Connection refused",
            retry_count=3,
            created_at=datetime(2025, 1, 1, 10, 2, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 10, 3, 0, tzinfo=UTC),
        )
        activity3 = ActivityExecution(
            id=uuid4(),
            execution_id=execution_id,
            activity_name="step-3-pending",
            node_type="approval",
            temporal_activity_id="step-3-pending",
            status=ActivityStatus.PENDING,
            started_at=None,
            completed_at=None,
            input_data={},
            output_data=None,
            error_details=None,
            retry_count=0,
            created_at=datetime(2025, 1, 1, 10, 4, 0, tzinfo=UTC),
            updated_at=datetime(2025, 1, 1, 10, 4, 0, tzinfo=UTC),
        )

        # First call: execution exists check
        mock_execution_result = Mock()
        mock_execution_result.one_or_none = Mock(return_value=execution)

        # Second call: three activities
        mock_activities_result = Mock()
        mock_activities_result.all = Mock(return_value=[activity1, activity2, activity3])

        mock_session.exec = AsyncMock(side_effect=[mock_execution_result, mock_activities_result])

        service = ExecutionService(session=mock_session, user=mock_user, temporal_service=None)
        result = await service.list_execution_activities(execution_id=execution_id, limit=10)

        assert len(result.resources) == 3

        # Verify first activity (completed script)
        assert result.resources[0].activity_name == "step-1-script"
        assert result.resources[0].status == ActivityStatus.COMPLETED
        assert result.resources[0].retry_count == 0
        assert result.resources[0].output_data == {"stdout": "hello"}
        assert result.resources[0].error_details is None

        # Verify second activity (failed HTTP with retries and error)
        assert result.resources[1].activity_name == "step-2-http"
        assert result.resources[1].status == ActivityStatus.FAILED
        assert result.resources[1].retry_count == 3
        assert result.resources[1].output_data is None
        assert result.resources[1].error_details == "Connection refused"

        # Verify third activity (pending approval)
        assert result.resources[2].activity_name == "step-3-pending"
        assert result.resources[2].status == ActivityStatus.PENDING
        assert result.resources[2].retry_count == 0
        assert result.resources[2].started_at is None
        assert result.resources[2].completed_at is None


class TestHandleActivityCallback(TestExecutionServiceBase):
    """Tests for handle_activity_callback method."""

    def _make_service(self) -> tuple[ExecutionService, AsyncMock]:
        """Create an ExecutionService with mocked temporal_service."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_user = Mock(spec=User)
        mock_user.id = uuid4()
        mock_temporal = AsyncMock()
        service = ExecutionService(mock_session, mock_user, temporal_service=mock_temporal)
        return service, mock_temporal

    @staticmethod
    def _mock_execution(temporal_workflow_id: str = "wf-123") -> Mock:
        """Create a mock execution with temporal_workflow_id."""
        mock_execution = Mock()
        mock_execution.temporal_workflow_id = temporal_workflow_id
        return mock_execution

    @pytest.mark.asyncio
    async def test_completes_activity_on_success_status(self) -> None:
        """Test that non-failed status calls complete_async_activity."""
        service, mock_temporal = self._make_service()
        service.get_execution = AsyncMock(return_value=self._mock_execution())  # type: ignore[method-assign]
        await service.handle_activity_callback(
            uuid4(),
            "node-1",
            {"status": "completed", "result": "ok"},
        )

        mock_temporal.complete_async_activity.assert_called_once()
        call_kwargs = mock_temporal.complete_async_activity.call_args.kwargs
        assert call_kwargs["result"] == {"output": {"status": "completed", "result": "ok"}}

    @pytest.mark.asyncio
    async def test_completes_activity_on_approved_status(self) -> None:
        """Test that approved status completes (not fails) the activity."""
        service, mock_temporal = self._make_service()
        service.get_execution = AsyncMock(return_value=self._mock_execution())  # type: ignore[method-assign]
        await service.handle_activity_callback(
            uuid4(),
            "approval-1",
            {"status": "approved", "approval_id": "apr-1"},
        )

        mock_temporal.complete_async_activity.assert_called_once()
        mock_temporal.fail_async_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_completes_activity_on_rejected_status(self) -> None:
        """Test that rejected status completes (not fails) the activity."""
        service, mock_temporal = self._make_service()
        service.get_execution = AsyncMock(return_value=self._mock_execution())  # type: ignore[method-assign]
        await service.handle_activity_callback(
            uuid4(),
            "approval-1",
            {"status": "rejected"},
        )

        mock_temporal.complete_async_activity.assert_called_once()
        mock_temporal.fail_async_activity.assert_not_called()

    @pytest.mark.asyncio
    async def test_fails_activity_on_failed_status(self) -> None:
        """Test that failed status calls fail_async_activity."""
        service, mock_temporal = self._make_service()
        service.get_execution = AsyncMock(return_value=self._mock_execution())  # type: ignore[method-assign]
        await service.handle_activity_callback(
            uuid4(),
            "node-1",
            {"status": "failed", "error": {"message": "LLM error", "error_type": "AgentError"}},
        )

        mock_temporal.fail_async_activity.assert_called_once()
        mock_temporal.complete_async_activity.assert_not_called()
        error = mock_temporal.fail_async_activity.call_args.kwargs["error"]
        assert "AgentError: LLM error" in str(error)

    @pytest.mark.asyncio
    async def test_failed_callback_uses_empty_signal_fallback_when_message_missing(self) -> None:
        """Empty/missing callback error.message uses the SIGNAL-02 fallback on the production path."""
        from syntara.workflows.workflow_engine.signals.processor import EMPTY_SIGNAL_ERROR_MESSAGE

        service, mock_temporal = self._make_service()
        service.get_execution = AsyncMock(return_value=self._mock_execution())  # type: ignore[method-assign]
        await service.handle_activity_callback(
            uuid4(),
            "node-1",
            {"status": "failed", "error": {}},
        )

        error = mock_temporal.fail_async_activity.call_args.kwargs["error"]
        assert error.message == EMPTY_SIGNAL_ERROR_MESSAGE
        assert "Activity execution failed" not in error.message

    @pytest.mark.asyncio
    async def test_failed_callback_uses_empty_signal_fallback_for_whitespace_message(self) -> None:
        """Whitespace-only callback error.message uses the SIGNAL-02 fallback."""
        from syntara.workflows.workflow_engine.signals.processor import EMPTY_SIGNAL_ERROR_MESSAGE

        service, mock_temporal = self._make_service()
        service.get_execution = AsyncMock(return_value=self._mock_execution())  # type: ignore[method-assign]
        await service.handle_activity_callback(
            uuid4(),
            "node-1",
            {"status": "failed", "error": {"message": "   ", "error_type": "AgentError"}},
        )

        error = mock_temporal.fail_async_activity.call_args.kwargs["error"]
        assert error.message == EMPTY_SIGNAL_ERROR_MESSAGE
        assert "AgentError:" not in error.message

    @pytest.mark.asyncio
    async def test_truncates_long_error_messages(self) -> None:
        """Test that error messages are truncated to 500 characters."""
        service, mock_temporal = self._make_service()
        service.get_execution = AsyncMock(return_value=self._mock_execution())  # type: ignore[method-assign]
        long_msg = "x" * 1000
        await service.handle_activity_callback(
            uuid4(),
            "node-1",
            {"status": "failed", "error": {"message": long_msg}},
        )

        error = mock_temporal.fail_async_activity.call_args.kwargs["error"]
        assert len(str(error)) <= 600  # type + ": " + 500 chars

    @pytest.mark.asyncio
    async def test_handles_non_dict_error_info(self) -> None:
        """Test that string error info is handled gracefully."""
        service, mock_temporal = self._make_service()
        service.get_execution = AsyncMock(return_value=self._mock_execution())  # type: ignore[method-assign]
        await service.handle_activity_callback(
            uuid4(),
            "node-1",
            {"status": "failed", "error": "plain string error"},
        )

        mock_temporal.fail_async_activity.assert_called_once()
        error = mock_temporal.fail_async_activity.call_args.kwargs["error"]
        assert "plain string error" in str(error)

    @pytest.mark.asyncio
    async def test_raises_temporal_unavailable_when_no_service(self) -> None:
        """Test that TemporalUnavailableError is raised when temporal_service is None."""
        from syntara.workflows.exceptions import TemporalUnavailableError

        mock_session = AsyncMock(spec=AsyncSession)
        mock_user = Mock(spec=User)
        mock_user.id = uuid4()
        service = ExecutionService(mock_session, mock_user, temporal_service=None)

        service.get_execution = AsyncMock(return_value=Mock())  # type: ignore[method-assign]
        with pytest.raises(TemporalUnavailableError):
            await service.handle_activity_callback(uuid4(), "node-1", {"status": "completed"})


class TestApplyTriggerSchemaDefaults:
    """Tests for _apply_trigger_schema_defaults static method."""

    MANUAL_TRIGGER: ClassVar[dict[str, Any]] = {
        "id": "trigger_1",
        "type": NodeType.MANUAL_TRIGGER,
        "parameters": {
            "input_schema": {
                "type": "object",
                "properties": {
                    "version": {"type": "string", "default": "latest"},
                    "timeout": {"type": "integer", "default": 30},
                },
            },
        },
    }

    def test_fills_defaults_for_empty_input(self) -> None:
        """Empty input_data gets all schema defaults applied."""
        data: dict[str, Any] = {}
        ExecutionService._apply_trigger_schema_defaults(self.MANUAL_TRIGGER, data)
        assert data == {"version": "latest", "timeout": 30}

    def test_preserves_user_values(self) -> None:
        """User-provided values are not overridden by defaults."""
        data: dict[str, Any] = {"version": "1.0"}
        ExecutionService._apply_trigger_schema_defaults(self.MANUAL_TRIGGER, data)
        assert data == {"version": "1.0", "timeout": 30}

    def test_validates_after_defaults(self) -> None:
        """Invalid input raises TriggerValidationError after defaults are applied."""
        trigger = {
            "id": "t",
            "type": NodeType.MANUAL_TRIGGER,
            "parameters": {
                "input_schema": {
                    "type": "object",
                    "properties": {"count": {"type": "integer", "default": 1}},
                    "required": ["count"],
                },
            },
        }
        data: dict[str, Any] = {"count": "not_an_integer"}
        with pytest.raises(TriggerValidationError, match="Trigger input validation failed"):
            ExecutionService._apply_trigger_schema_defaults(trigger, data)

    def test_webhook_targets_input_directly(self) -> None:
        """For webhook triggers, defaults are applied to input_data directly."""
        trigger = {
            "id": "t",
            "type": NodeType.WEBHOOK_TRIGGER,
            "parameters": {
                "input_schema": {
                    "type": "object",
                    "properties": {"event": {"type": "string", "default": "push"}},
                },
            },
        }
        data: dict[str, Any] = {}
        ExecutionService._apply_trigger_schema_defaults(trigger, data)
        assert data == {"event": "push"}

    def test_eda_targets_input_directly(self) -> None:
        """For EDA triggers, defaults are applied to input_data directly."""
        trigger = {
            "id": "t",
            "type": NodeType.EDA_TRIGGER,
            "parameters": {
                "input_schema": {
                    "type": "object",
                    "properties": {"source": {"type": "string", "default": "alertmanager"}},
                },
            },
        }
        data: dict[str, Any] = {}
        ExecutionService._apply_trigger_schema_defaults(trigger, data)
        assert data == {"source": "alertmanager"}

    def test_no_input_schema_is_noop(self) -> None:
        """Trigger without input_schema leaves input_data unchanged."""
        trigger = {"id": "t", "type": NodeType.MANUAL_TRIGGER, "parameters": {}}
        data = {"key": "value"}
        ExecutionService._apply_trigger_schema_defaults(trigger, data)
        assert data == {"key": "value"}

    def test_trigger_without_parameters_is_noop(self) -> None:
        """Trigger with no parameters key leaves input_data unchanged."""
        trigger: dict[str, Any] = {"id": "t", "type": NodeType.MANUAL_TRIGGER}
        data = {"key": "value"}
        ExecutionService._apply_trigger_schema_defaults(trigger, data)
        assert data == {"key": "value"}

    def test_ref_in_schema_raises_validation_error(self) -> None:
        """Schema with $ref raises TriggerValidationError (SSRF prevention)."""
        trigger = {
            "id": "t",
            "type": NodeType.MANUAL_TRIGGER,
            "parameters": {
                "input_schema": {
                    "type": "object",
                    "properties": {"data": {"$ref": "http://internal-service/secret"}},
                },
            },
        }
        with pytest.raises(TriggerValidationError):
            ExecutionService._apply_trigger_schema_defaults(trigger, {"data": "test"})

    def test_webhook_empty_input_gets_defaults(self) -> None:
        """Webhook trigger with empty input gets schema defaults applied."""
        trigger = {
            "id": "t",
            "type": NodeType.WEBHOOK_TRIGGER,
            "parameters": {
                "input_schema": {
                    "type": "object",
                    "properties": {"event": {"type": "string", "default": "push"}},
                },
            },
        }
        data: dict[str, Any] = {}
        ExecutionService._apply_trigger_schema_defaults(trigger, data)
        assert data == {"event": "push"}
