"""Unit tests for MonitoringWorkflowInterceptor."""

from datetime import timedelta
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from temporalio.worker import WorkflowInboundInterceptor, WorkflowInterceptorClassInput

from syntara.workflows.workflow_engine.interceptors.monitoring_interceptor import (
    MonitoringWorkflowInterceptor,
    _MonitoringWorkflowInboundInterceptor,
)


class TestMonitoringWorkflowInterceptor:
    """Test MonitoringWorkflowInterceptor class."""

    def test_workflow_interceptor_class_returns_inbound_interceptor(self) -> None:
        """Test workflow_interceptor_class returns the inbound interceptor class."""
        interceptor = MonitoringWorkflowInterceptor()
        mock_input = Mock(spec=WorkflowInterceptorClassInput)

        result = interceptor.workflow_interceptor_class(mock_input)

        assert result == _MonitoringWorkflowInboundInterceptor
        assert issubclass(result, WorkflowInboundInterceptor)


class TestMonitoringWorkflowInboundInterceptor:
    """Test _MonitoringWorkflowInboundInterceptor class."""

    @pytest.mark.asyncio
    async def test_execute_workflow_starts_monitoring_activity(self) -> None:
        """Test execute_workflow starts activity monitoring."""
        execution_id = str(uuid4())
        temporal_workflow_id = "workflow-123"

        mock_input = Mock(spec=WorkflowInterceptorClassInput)
        mock_input.args = [{"schema_version": "2.0.0"}, execution_id, {"input": "data"}]

        mock_workflow_info = Mock()
        mock_workflow_info.workflow_id = temporal_workflow_id
        mock_workflow_info.workflow_type = "orchestrator_workflow"

        mock_start_activity = Mock()

        interceptor = _MonitoringWorkflowInboundInterceptor(Mock())

        with (
            patch("temporalio.workflow.info", return_value=mock_workflow_info),
            patch("temporalio.workflow.start_activity", return_value=mock_start_activity) as mock_start,
        ):
            mock_next_execute = AsyncMock(return_value="workflow_result")
            interceptor.next = Mock()
            interceptor.next.execute_workflow = mock_next_execute

            result = await interceptor.execute_workflow(mock_input)

            mock_start.assert_called_once()
            call_args = mock_start.call_args

            assert call_args.args[0] == "register_activity_monitoring"
            assert call_args.kwargs["args"] == [execution_id, temporal_workflow_id, None]
            assert call_args.kwargs["activity_id"] == "__internal__register_monitoring"
            assert call_args.kwargs["start_to_close_timeout"] == timedelta(seconds=30)
            assert call_args.kwargs["retry_policy"] is None

            mock_next_execute.assert_awaited_once_with(mock_input)
            assert result == "workflow_result"

    @pytest.mark.asyncio
    async def test_execute_workflow_handles_insufficient_args(self) -> None:
        """Test execute_workflow handles case when args are insufficient."""
        mock_input = Mock(spec=WorkflowInterceptorClassInput)
        mock_input.args = [{"schema_version": "2.0.0"}]

        interceptor = _MonitoringWorkflowInboundInterceptor(Mock())

        mock_start_activity = Mock()

        with patch("temporalio.workflow.start_activity", return_value=mock_start_activity) as mock_start:
            mock_next_execute = AsyncMock(return_value="workflow_result")
            interceptor.next = Mock()
            interceptor.next.execute_workflow = mock_next_execute

            result = await interceptor.execute_workflow(mock_input)

            mock_start.assert_not_called()

            mock_next_execute.assert_awaited_once_with(mock_input)
            assert result == "workflow_result"

    @pytest.mark.asyncio
    async def test_execute_workflow_skips_non_orchestrator_workflow_types(self) -> None:
        """Interceptor must skip non-orchestrator_workflow types (e.g. scheduled_workflow_launcher)."""
        mock_input = Mock(spec=WorkflowInterceptorClassInput)
        mock_input.args = ["workflow-id-string", "trigger_schedule"]

        mock_workflow_info = Mock()
        mock_workflow_info.workflow_id = "scheduled_workflow_launcher-abc123"
        mock_workflow_info.workflow_type = "scheduled_workflow_launcher"

        interceptor = _MonitoringWorkflowInboundInterceptor(Mock())

        with (
            patch("temporalio.workflow.info", return_value=mock_workflow_info),
            patch("temporalio.workflow.start_activity") as mock_start,
        ):
            mock_next_execute = AsyncMock(return_value="launcher_result")
            interceptor.next = Mock()
            interceptor.next.execute_workflow = mock_next_execute

            result = await interceptor.execute_workflow(mock_input)

            # Must NOT attempt to schedule monitoring for this workflow type —
            # args[1] ("trigger_schedule") is not a valid execution_id UUID.
            mock_start.assert_not_called()
            mock_next_execute.assert_awaited_once_with(mock_input)
            assert result == "launcher_result"

    @pytest.mark.asyncio
    async def test_execute_workflow_continues_on_monitoring_failure(self) -> None:
        """Test execute_workflow continues normal execution even if monitoring setup fails."""
        execution_id = str(uuid4())
        temporal_workflow_id = "workflow-123"

        mock_input = Mock(spec=WorkflowInterceptorClassInput)
        mock_input.args = [{"schema_version": "2.0.0"}, execution_id, {"input": "data"}]

        mock_workflow_info = Mock()
        mock_workflow_info.workflow_id = temporal_workflow_id
        mock_workflow_info.workflow_type = "orchestrator_workflow"

        interceptor = _MonitoringWorkflowInboundInterceptor(Mock())

        with (
            patch("temporalio.workflow.info", return_value=mock_workflow_info),
            patch("temporalio.workflow.start_activity", side_effect=Exception("Monitoring failed")),
        ):
            mock_next_execute = AsyncMock(return_value="workflow_result")
            interceptor.next = Mock()
            interceptor.next.execute_workflow = mock_next_execute

            with pytest.raises(Exception, match="Monitoring failed"):
                await interceptor.execute_workflow(mock_input)

    @pytest.mark.asyncio
    async def test_execute_workflow_extracts_execution_id_from_correct_position(self) -> None:
        """Test execute_workflow extracts execution_id from second argument."""
        execution_id = str(uuid4())
        temporal_workflow_id = "workflow-123"
        workflow_def = {"schema_version": "2.0.0", "triggers": [], "nodes": [], "edges": []}
        input_data = {"key": "value"}

        mock_input = Mock(spec=WorkflowInterceptorClassInput)
        mock_input.args = [workflow_def, execution_id, input_data]

        mock_workflow_info = Mock()
        mock_workflow_info.workflow_id = temporal_workflow_id
        mock_workflow_info.workflow_type = "orchestrator_workflow"

        mock_start_activity = Mock()

        interceptor = _MonitoringWorkflowInboundInterceptor(Mock())

        with (
            patch("temporalio.workflow.info", return_value=mock_workflow_info),
            patch("temporalio.workflow.start_activity", return_value=mock_start_activity) as mock_start,
        ):
            mock_next_execute = AsyncMock(return_value="workflow_result")
            interceptor.next = Mock()
            interceptor.next.execute_workflow = mock_next_execute

            await interceptor.execute_workflow(mock_input)

            call_args = mock_start.call_args
            assert call_args.kwargs["args"] == [execution_id, temporal_workflow_id, None]

    @pytest.mark.asyncio
    async def test_execute_workflow_uses_non_blocking_start_activity(self) -> None:
        """Test execute_workflow uses start_activity (non-blocking) not execute_activity."""
        execution_id = str(uuid4())
        temporal_workflow_id = "workflow-123"

        mock_input = Mock(spec=WorkflowInterceptorClassInput)
        mock_input.args = [{"schema_version": "2.0.0"}, execution_id, {"input": "data"}]

        mock_workflow_info = Mock()
        mock_workflow_info.workflow_id = temporal_workflow_id
        mock_workflow_info.workflow_type = "orchestrator_workflow"

        mock_start_activity = Mock()

        interceptor = _MonitoringWorkflowInboundInterceptor(Mock())

        with (
            patch("temporalio.workflow.info", return_value=mock_workflow_info),
            patch("temporalio.workflow.start_activity", return_value=mock_start_activity) as mock_start,
            patch("temporalio.workflow.execute_activity") as mock_execute,
        ):
            mock_next_execute = AsyncMock(return_value="workflow_result")
            interceptor.next = Mock()
            interceptor.next.execute_workflow = mock_next_execute

            await interceptor.execute_workflow(mock_input)

            mock_start.assert_called_once()
            mock_execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_workflow_timeout_configuration(self) -> None:
        """Test execute_workflow configures 30 second timeout for monitoring activity."""
        execution_id = str(uuid4())
        temporal_workflow_id = "workflow-123"

        mock_input = Mock(spec=WorkflowInterceptorClassInput)
        mock_input.args = [{"schema_version": "2.0.0"}, execution_id, {"input": "data"}]

        mock_workflow_info = Mock()
        mock_workflow_info.workflow_id = temporal_workflow_id
        mock_workflow_info.workflow_type = "orchestrator_workflow"

        mock_start_activity = Mock()

        interceptor = _MonitoringWorkflowInboundInterceptor(Mock())

        with (
            patch("temporalio.workflow.info", return_value=mock_workflow_info),
            patch("temporalio.workflow.start_activity", return_value=mock_start_activity) as mock_start,
        ):
            mock_next_execute = AsyncMock(return_value="workflow_result")
            interceptor.next = Mock()
            interceptor.next.execute_workflow = mock_next_execute

            await interceptor.execute_workflow(mock_input)

            call_kwargs = mock_start.call_args.kwargs
            assert call_kwargs["start_to_close_timeout"] == timedelta(seconds=30)
            assert call_kwargs["retry_policy"] is None

    @pytest.mark.asyncio
    async def test_execute_workflow_preserves_workflow_result(self) -> None:
        """Test execute_workflow preserves and returns the original workflow result."""
        execution_id = str(uuid4())
        expected_result = {"status": "completed", "data": [1, 2, 3]}

        mock_input = Mock(spec=WorkflowInterceptorClassInput)
        mock_input.args = [{"schema_version": "2.0.0"}, execution_id, {}]

        mock_workflow_info = Mock()
        mock_workflow_info.workflow_id = "workflow-123"
        mock_workflow_info.workflow_type = "orchestrator_workflow"

        interceptor = _MonitoringWorkflowInboundInterceptor(Mock())

        with (
            patch("temporalio.workflow.info", return_value=mock_workflow_info),
            patch("temporalio.workflow.start_activity", return_value=Mock()),
        ):
            mock_next_execute = AsyncMock(return_value=expected_result)
            interceptor.next = Mock()
            interceptor.next.execute_workflow = mock_next_execute

            result = await interceptor.execute_workflow(mock_input)

            assert result == expected_result
