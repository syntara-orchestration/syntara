"""Unit tests for ExecutionService.retry_execution method."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.models import User
from syntara.workflows.exceptions import (
    ExecutionNotFoundError,
    ExecutionNotRetryableError,
)
from syntara.workflows.models.execution import Execution, ExecutionMode, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.execution_service import ExecutionService
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService


def _make_execution(
    status: ExecutionStatus,
    mode: ExecutionMode = ExecutionMode.STANDARD,
) -> Execution:
    execution = Mock(spec=Execution)
    execution.id = uuid4()
    execution.status = status
    execution.mode = mode
    execution.workflow_id = uuid4()
    execution.workflow_version_id = uuid4()
    execution.project_id = uuid4()
    execution.temporal_workflow_id = f"temporal-{execution.id}"
    execution.input_data = {"key": "value"}
    execution.trigger_node_id = "trigger-1"
    execution.deleted_at = None

    workflow = Mock(spec=Workflow)
    workflow.id = execution.workflow_id
    workflow.name = "test-workflow"
    workflow.project_id = execution.project_id
    workflow.published_version = 1
    workflow.created_by = uuid4()
    workflow.deleted_at = None
    execution.workflow = workflow

    return execution


def _make_version(version_id=None) -> WorkflowVersion:
    version = Mock(spec=WorkflowVersion)
    version.id = version_id or uuid4()
    version.version = 1
    version.workflow_definition = {
        "triggers": [{"id": "trigger-1", "type": "manual_trigger", "parameters": {}}],
        "nodes": [],
        "edges": [],
    }
    return version


def _mock_session_with_two_queries(
    execution: Execution | None,
    version: WorkflowVersion | None,
) -> tuple[AsyncSession, Mock]:
    """Mock session that returns execution on first exec(), version on second.

    Returns the session and a separate Mock for .add() so callers can assert on it.
    """
    exec_result = Mock()
    exec_result.one_or_none.return_value = execution

    version_result = Mock()
    version_result.one_or_none.return_value = version

    add_mock = Mock()
    mock_session = Mock(spec=AsyncSession)
    mock_session.exec = AsyncMock(side_effect=[exec_result, version_result])
    mock_session.add = add_mock
    mock_session.commit = AsyncMock()
    return mock_session, add_mock


class TestRetryExecution:
    """Test retry_execution method."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "execution_status",
        [
            ExecutionStatus.COMPLETED,
            ExecutionStatus.COMPLETED_WITH_ERRORS,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        ],
    )
    async def test_retry_execution_success(self, execution_status: ExecutionStatus) -> None:
        """Test successful retry for each terminal status."""
        execution = _make_execution(execution_status)
        version = _make_version(execution.workflow_version_id)
        mock_session, add_mock = _mock_session_with_two_queries(execution, version)
        mock_user = Mock(spec=User)
        mock_user.id = uuid4()
        mock_user.display_name = "Test User"

        mock_temporal = Mock(spec=TemporalExecutionService)
        temporal_result = Mock()
        temporal_result.temporal_workflow_id = f"temporal-new-{uuid4()}"
        temporal_result.execution_id = str(uuid4())
        mock_temporal.start_workflow = AsyncMock(return_value=temporal_result)

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
            patch.object(service, "convert_resource_mixin") as mock_convert,
        ):
            mock_convert.convert_resource.return_value = Mock()
            await service.retry_execution(execution.id)

        mock_temporal.start_workflow.assert_awaited_once()
        call_kwargs = mock_temporal.start_workflow.call_args[1]
        assert call_kwargs["input_data"] == execution.input_data
        assert call_kwargs["workflow_name"] == execution.workflow.name

        add_mock.assert_called_once()
        added_execution = add_mock.call_args[0][0]
        assert added_execution.retried_from_execution_id == execution.id
        assert added_execution.workflow_version_id == version.id
        assert added_execution.input_data == execution.input_data
        assert added_execution.trigger_node_id == "trigger-1"
        assert added_execution.status == ExecutionStatus.PENDING

    @pytest.mark.asyncio
    async def test_retry_execution_not_found(self) -> None:
        """Test retry when execution not found raises domain exception."""
        exec_result = Mock()
        exec_result.one_or_none.return_value = None
        mock_session = Mock(spec=AsyncSession)
        mock_session.exec = AsyncMock(return_value=exec_result)
        mock_user = Mock(spec=User)

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=None,
        )

        non_existent_id = uuid4()
        with pytest.raises(ExecutionNotFoundError) as exc_info:
            await service.retry_execution(non_existent_id)

        assert exc_info.value.execution_id == non_existent_id

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "non_terminal_status",
        [
            ExecutionStatus.PENDING,
            ExecutionStatus.RUNNING,
            ExecutionStatus.PAUSED,
        ],
    )
    async def test_retry_execution_non_terminal_state(self, non_terminal_status: ExecutionStatus) -> None:
        """Test retry when execution is not in terminal state raises exception."""
        execution = _make_execution(non_terminal_status)
        exec_result = Mock()
        exec_result.one_or_none.return_value = execution
        mock_session = Mock(spec=AsyncSession)
        mock_session.exec = AsyncMock(return_value=exec_result)
        mock_user = Mock(spec=User)

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=None,
        )

        with pytest.raises(ExecutionNotRetryableError) as exc_info:
            await service.retry_execution(execution.id)

        assert exc_info.value.execution_id == execution.id
        assert "must be terminal" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_retry_execution_test_mode_rejected(self) -> None:
        """Test retry when execution is a test run raises exception."""
        execution = _make_execution(ExecutionStatus.FAILED, mode=ExecutionMode.TEST)
        exec_result = Mock()
        exec_result.one_or_none.return_value = execution
        mock_session = Mock(spec=AsyncSession)
        mock_session.exec = AsyncMock(return_value=exec_result)
        mock_user = Mock(spec=User)

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=None,
        )

        with pytest.raises(ExecutionNotRetryableError) as exc_info:
            await service.retry_execution(execution.id)

        assert exc_info.value.execution_id == execution.id
        assert "test" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_retry_execution_without_temporal(self) -> None:
        """Test retry works without Temporal (uses stub workflow ID)."""
        execution = _make_execution(ExecutionStatus.FAILED)
        version = _make_version(execution.workflow_version_id)
        mock_session, add_mock = _mock_session_with_two_queries(execution, version)
        mock_user = Mock(spec=User)
        mock_user.id = uuid4()
        mock_user.display_name = "Test User"

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=None,
        )

        with (
            patch(
                "syntara.workflows.services.execution_service.resolve_user_display_name",
                new_callable=AsyncMock,
                return_value="Author",
            ),
            patch.object(service, "convert_resource_mixin") as mock_convert,
        ):
            mock_convert.convert_resource.return_value = Mock()
            await service.retry_execution(execution.id)

        add_mock.assert_called_once()
        added_execution = add_mock.call_args[0][0]
        assert added_execution.temporal_workflow_id.startswith("exec-")

    @pytest.mark.asyncio
    async def test_retry_execution_deleted_workflow_version(self) -> None:
        """Test retry when workflow version no longer exists."""
        execution = _make_execution(ExecutionStatus.FAILED)
        mock_session, _ = _mock_session_with_two_queries(execution, None)
        mock_user = Mock(spec=User)

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=None,
        )

        with pytest.raises(ExecutionNotRetryableError) as exc_info:
            await service.retry_execution(execution.id)

        assert exc_info.value.execution_id == execution.id
        assert "workflow version no longer exists" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_retry_execution_soft_deleted_workflow(self) -> None:
        """Test retry when workflow has been soft-deleted."""
        execution = _make_execution(ExecutionStatus.FAILED)
        execution.workflow.deleted_at = datetime.now(UTC)
        exec_result = Mock()
        exec_result.one_or_none.return_value = execution
        mock_session = Mock(spec=AsyncSession)
        mock_session.exec = AsyncMock(return_value=exec_result)
        mock_user = Mock(spec=User)

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=None,
        )

        with pytest.raises(ExecutionNotRetryableError) as exc_info:
            await service.retry_execution(execution.id)

        assert exc_info.value.execution_id == execution.id
        assert "deleted" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_retry_execution_cancels_temporal_on_db_failure(self) -> None:
        """Test that Temporal workflow is cancelled when DB commit fails."""
        execution = _make_execution(ExecutionStatus.FAILED)
        version = _make_version(execution.workflow_version_id)

        exec_result = Mock()
        exec_result.one_or_none.return_value = execution
        version_result = Mock()
        version_result.one_or_none.return_value = version
        mock_session = Mock(spec=AsyncSession)
        mock_session.exec = AsyncMock(side_effect=[exec_result, version_result])
        mock_session.add = Mock()
        mock_session.commit = AsyncMock(side_effect=Exception("DB commit failed"))
        mock_user = Mock(spec=User)
        mock_user.id = uuid4()
        mock_user.display_name = "Test User"

        mock_temporal = Mock(spec=TemporalExecutionService)
        temporal_result = Mock()
        temporal_result.temporal_workflow_id = f"temporal-new-{uuid4()}"
        temporal_result.execution_id = str(uuid4())
        mock_temporal.start_workflow = AsyncMock(return_value=temporal_result)
        mock_temporal.cancel_workflow = AsyncMock()

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
            await service.retry_execution(execution.id)

        mock_temporal.cancel_workflow.assert_awaited_once_with(
            temporal_workflow_id=temporal_result.temporal_workflow_id
        )
