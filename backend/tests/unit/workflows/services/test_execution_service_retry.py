"""Unit tests for ExecutionService.retry_execution method."""

from typing import cast
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.audit.dispatcher import AuditEventDispatcher
from syntara.audit.emitter import request_id_context_var
from syntara.core.exceptions import SafeValueError
from syntara.core.models import User
from syntara.workflows.exceptions import (
    ExecutionNotFoundError,
    ExecutionNotRetryableError,
)
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionMode, ExecutionStatus
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.services.execution_service import ExecutionService
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
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

    workflow = Mock(spec=Workflow)
    workflow.id = execution.workflow_id
    workflow.name = "test-workflow"
    workflow.project_id = execution.project_id
    workflow.published_version = 1
    workflow.created_by = uuid4()
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


def _raise_for_retry_requested(event: object) -> None:
    """Simulate telemetry failure without affecting lifecycle events."""
    if event.__class__.__name__ == "WorkflowRetryRequestedEvent":
        raise RuntimeError from None


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
            patch(
                "syntara.workflows.services.execution_service.AuditEventDispatcher.dispatch",
                side_effect=_raise_for_retry_requested,
            ),
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
        assert added_execution.execution_metadata is None

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


class TestFailedStepTypes:
    """Test failed-step telemetry normalization."""

    @pytest.mark.asyncio
    async def test_uses_failed_activity_node_types(self) -> None:
        failed_script = Mock(spec=ActivityExecution)
        failed_script.status = ActivityStatus.FAILED
        failed_script.activity_name = "workflow-node-id"
        failed_script.node_type = NodeType.SCRIPT

        failed_http = Mock(spec=ActivityExecution)
        failed_http.status = ActivityStatus.FAILED
        failed_http.activity_name = "another-node-id#iter-1"
        failed_http.node_type = NodeType.HTTP_REQUEST

        result = Mock()
        result.all.return_value = [failed_script, failed_http]
        session = Mock(spec=AsyncSession)
        session.exec = AsyncMock(return_value=result)

        step_types = await ExecutionService._get_failed_step_types(session, uuid4())

        assert step_types == ["http_request", "script"]

    @pytest.mark.asyncio
    async def test_bounds_normalized_failed_activity_node_types(self) -> None:
        """Failed step telemetry is sorted and capped at 50 node types."""
        activities = []
        for index in range(52):
            activity = Mock(spec=ActivityExecution)
            activity.status = ActivityStatus.FAILED
            activity.node_type = Mock(value=f"type_{index:02d}")
            activities.append(activity)

        result = Mock()
        result.all.return_value = activities
        session = Mock(spec=AsyncSession)
        session.exec = AsyncMock(return_value=result)

        step_types = await ExecutionService._get_failed_step_types(session, uuid4())

        assert len(step_types) == 50
        assert step_types == sorted(step_types)
        assert step_types == [f"type_{index:02d}" for index in range(50)]


class TestRetryRejectionMetrics:
    """Test retry rejection metrics are recorded for all failure paths."""

    @pytest.mark.asyncio
    async def test_plain_retry_records_rejection_for_nonexistent_execution(self) -> None:
        """Standard retry records rejection metric when execution not found."""
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
        with (
            patch.object(service, "_record_retry_request") as mock_record,
            pytest.raises(ExecutionNotFoundError),
        ):
            await service.retry_execution(non_existent_id)

        mock_record.assert_called_once_with("standard", "rejected")

    @pytest.mark.asyncio
    async def test_retry_from_failure_records_rejection_for_nonexistent_execution(self) -> None:
        """Retry-from-failure records rejection metric when execution not found."""
        mock_session = Mock(spec=AsyncSession)
        mock_user = Mock(spec=User)

        service = ExecutionService(
            session=mock_session,
            user=mock_user,
            temporal_service=None,
        )

        non_existent_id = uuid4()
        with (
            patch(
                "syntara.workflows.services.execution_service.validate_retry_from_failure",
                new_callable=AsyncMock,
                side_effect=ExecutionNotFoundError(non_existent_id),
            ),
            patch.object(service, "_record_retry_request") as mock_record,
            pytest.raises(ExecutionNotFoundError),
        ):
            await service.retry_from_failure(non_existent_id, ["node-1"])

        mock_record.assert_called_once_with("from_failure", "rejected")


class TestRetryMetadata:
    """Test metadata used to infer retry kind."""

    @pytest.mark.asyncio
    async def test_retry_from_failure_persists_eligible_point_ids(self) -> None:
        """Retry-from-failure stores eligible points on the new execution."""
        source = _make_execution(ExecutionStatus.FAILED)
        version = _make_version(source.workflow_version_id)
        version.workflow_definition["nodes"] = [{"id": "node-1"}, {"id": "node-2"}, {"id": "node-3"}]
        query_results = []
        for value in (source, source.workflow, version):
            result = Mock()
            result.one_or_none.return_value = value
            query_results.append(result)

        add_mock = Mock()
        mock_session = Mock(spec=AsyncSession)
        mock_session.exec = AsyncMock(side_effect=query_results)
        mock_session.add = add_mock
        commit_mock = AsyncMock()
        mock_session.commit = commit_mock
        user = Mock(spec=User)
        user.id = uuid4()
        user.display_name = "Test User"
        service = ExecutionService(session=mock_session, user=user, temporal_service=None)
        validation = Mock(eligible=True, eligible_point_ids=["node-1", "node-2"])

        request_id = uuid4()
        request_token = request_id_context_var.set(request_id)

        def dispatch_after_commit(_event: object) -> None:
            assert commit_mock.await_count == 1

        try:
            with (
                patch(
                    "syntara.workflows.services.execution_service.validate_retry_from_failure",
                    new_callable=AsyncMock,
                    return_value=validation,
                ),
                patch(
                    "syntara.workflows.services.execution_service.resolve_user_display_name",
                    new_callable=AsyncMock,
                    return_value="Author",
                ),
                patch.object(service, "_to_read", new_callable=AsyncMock, side_effect=lambda execution: execution),
                patch.object(
                    service,
                    "_get_failed_step_types",
                    new_callable=AsyncMock,
                    return_value=["http_request", "script"],
                ),
                patch(
                    "syntara.workflows.services.execution_service.AuditEventDispatcher.dispatch",
                    side_effect=dispatch_after_commit,
                ) as mock_dispatch,
            ):
                await service.retry_from_failure(source.id, ["node-1", "node-2"])
        finally:
            request_id_context_var.reset(request_token)

        add_mock.assert_called_once()
        added_execution = add_mock.call_args[0][0]
        assert added_execution.retried_from_execution_id == source.id
        assert added_execution.execution_metadata == {"eligible_point_ids": ["node-1", "node-2"]}
        event = mock_dispatch.call_args.args[0]
        assert event.execution_id == added_execution.id
        assert event.source_execution_id == source.id
        assert event.retry_kind == "from_failure"
        assert event.node_count == 3
        assert event.failed_step_types == ["http_request", "script"]
        assert event.request_id == request_id


class TestRetryRequestedEvent:
    """Test accepted retry event payloads."""

    @pytest.mark.asyncio
    async def test_standard_retry_dispatches_event_after_persistence(self) -> None:
        """Standard retries dispatch an event with source and new execution IDs."""
        execution = _make_execution(ExecutionStatus.FAILED)
        version = _make_version(execution.workflow_version_id)
        mock_session, add_mock = _mock_session_with_two_queries(execution, version)
        commit_mock = cast("AsyncMock", mock_session.commit)
        user = Mock(spec=User)
        user.id = uuid4()
        user.display_name = "Test User"
        service = ExecutionService(session=mock_session, user=user, temporal_service=None)
        request_id = uuid4()
        request_token = request_id_context_var.set(request_id)

        def dispatch_after_commit(_event: object) -> None:
            assert commit_mock.await_count == 1

        try:
            with (
                patch(
                    "syntara.workflows.services.execution_service.resolve_user_display_name",
                    new_callable=AsyncMock,
                    return_value="Author",
                ),
                patch.object(service, "_to_read", new_callable=AsyncMock, side_effect=lambda execution: execution),
                patch(
                    "syntara.workflows.services.execution_service.AuditEventDispatcher.dispatch",
                    side_effect=dispatch_after_commit,
                ) as mock_dispatch,
            ):
                await service.retry_execution(execution.id)
        finally:
            request_id_context_var.reset(request_token)

        added_execution = add_mock.call_args.args[0]
        event = mock_dispatch.call_args.args[0]
        assert event.execution_id == added_execution.id
        assert event.source_execution_id == execution.id
        assert event.retry_kind == "standard"
        assert event.node_count is None
        assert event.failed_step_types == []
        assert event.request_id == request_id
        assert commit_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_plain_retry_records_rejection_for_missing_trigger_node(self) -> None:
        """Standard retry records rejection when the retained trigger is missing."""
        execution = _make_execution(ExecutionStatus.FAILED)
        version = _make_version(execution.workflow_version_id)
        version.workflow_definition = {"triggers": [], "nodes": [], "edges": []}
        mock_session, _ = _mock_session_with_two_queries(execution, version)
        service = ExecutionService(session=mock_session, user=Mock(spec=User), temporal_service=None)

        with (
            patch.object(service, "_record_retry_request") as mock_record,
            patch.object(AuditEventDispatcher, "dispatch") as mock_dispatch,
            pytest.raises(SafeValueError),
        ):
            await service.retry_execution(execution.id)

        mock_record.assert_called_once_with("standard", "rejected")
        mock_dispatch.assert_not_called()

    @pytest.mark.asyncio
    async def test_retry_from_failure_records_rejection_for_missing_trigger_node(self) -> None:
        """Retry-from-failure records rejection when the retained trigger is missing."""
        source = _make_execution(ExecutionStatus.FAILED)
        version = _make_version(source.workflow_version_id)
        version.workflow_definition = {"triggers": [], "nodes": [], "edges": []}

        def result_for(value: object) -> Mock:
            result = Mock()
            result.one_or_none.return_value = value
            return result

        mock_session = Mock(spec=AsyncSession)
        mock_session.exec = AsyncMock(
            side_effect=[
                result_for(source),
                result_for(source.workflow),
                result_for(version),
            ]
        )
        service = ExecutionService(session=mock_session, user=Mock(spec=User), temporal_service=None)

        validation = Mock(eligible=True, eligible_point_ids=["node-1"])
        with (
            patch(
                "syntara.workflows.services.execution_service.validate_retry_from_failure",
                new_callable=AsyncMock,
                return_value=validation,
            ),
            patch.object(service, "_record_retry_request") as mock_record,
            patch.object(AuditEventDispatcher, "dispatch") as mock_dispatch,
            pytest.raises(SafeValueError),
        ):
            await service.retry_from_failure(source.id, ["node-1"])

        mock_record.assert_called_once_with("from_failure", "rejected")
        mock_dispatch.assert_not_called()
