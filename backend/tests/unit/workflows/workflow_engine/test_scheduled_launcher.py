"""Tests for ScheduledExecutionLauncher metadata and metrics.

Covers:
- execution_metadata populated with trigger_type, schedule_id, scheduled_at, triggered_at
- Prometheus metrics recorded on success and failure
- Timing captured from activity.info()
- Setup activity returns child workflow data without calling TemporalExecutionService
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from temporalio.exceptions import ApplicationError

from syntara.core.models.principal import service_principal_id
from syntara.metrics.types import MetricType
from syntara.workflows.exceptions import WorkflowNotPublishedError
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName
from syntara.workflows.workflow_engine.scheduled_launcher import ScheduledExecutionLauncher


def _make_launcher() -> ScheduledExecutionLauncher:
    """Create a launcher with a mock session factory."""
    session_factory = MagicMock()
    return ScheduledExecutionLauncher(
        session_factory=session_factory,
        task_queue="test-queue",
    )


def _make_mock_activity_info(
    scheduled_time: datetime | None = None,
    started_time: datetime | None = None,
) -> MagicMock:
    """Create a mock activity.info() return value."""
    info = MagicMock()
    info.scheduled_time = scheduled_time or datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
    info.started_time = started_time or datetime(2024, 1, 1, 9, 0, 5, tzinfo=UTC)
    return info


class TestExecutionMetadata:
    """Tests for execution_metadata population."""

    async def test_create_execution_sets_trigger_type(self) -> None:
        """Execution metadata should include trigger_type as ActivityName enum."""
        launcher = _make_launcher()
        workflow_id = uuid4()
        scheduled_at = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        triggered_at = datetime(2024, 1, 1, 9, 0, 3, tzinfo=UTC)
        service_identity = "backend.ao.svc"

        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.name = "test-workflow"
        mock_workflow.project_id = uuid4()
        mock_workflow.created_by = uuid4()
        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "triggers": [],
            "nodes": [],
            "edges": [],
        }

        with (
            patch.object(launcher, "_load_published_workflow", return_value=(mock_workflow, mock_version)),
            patch("syntara.workflows.workflow_engine.scheduled_launcher.get_settings") as mock_get_settings,
            patch(
                "syntara.workflows.workflow_engine.scheduled_launcher.resolve_user_display_name",
                return_value="Author Name",
            ),
        ):
            mock_get_settings.return_value.service_identity = service_identity
            mock_get_settings.return_value.max_concurrent_workflows = 0

            mock_session = AsyncMock()
            launcher._session_factory = MagicMock()
            launcher._session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            launcher._session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await launcher._create_execution(workflow_id, "trigger_1", scheduled_at, triggered_at)

        # Verify execution was added to session
        mock_session.add.assert_called_once()
        execution = mock_session.add.call_args[0][0]

        # Verify created_by/updated_by use service_principal_id
        expected_principal_id = service_principal_id(service_identity)
        assert execution.created_by == expected_principal_id
        assert execution.updated_by == expected_principal_id

        # Verify trigger_type and interface fields on the execution itself
        assert execution.trigger_type == "scheduled_trigger"
        assert execution.interface is None

        # Verify execution_metadata
        metadata = execution.execution_metadata
        assert metadata is not None
        assert metadata["trigger_type"] == ActivityName.SCHEDULED_TRIGGER
        assert metadata["schedule_id"] == f"orchestrator-sched-{workflow_id}-trigger_1"
        assert metadata["scheduled_at"] == scheduled_at.isoformat()
        assert metadata["triggered_at"] == triggered_at.isoformat()

        assert result["execution_id"] is not None
        assert result["temporal_workflow_id"] == f"test-workflow-{result['execution_id']}"

        # Verify workflow_metadata is returned for child workflow start
        wf_meta = result["workflow_metadata"]
        assert wf_meta["workflow_context"]["workflow"]["project_id"] == str(mock_workflow.project_id)
        assert wf_meta["workflow_context"]["workflow"]["name"] == "test-workflow"
        assert wf_meta["workflow_context"]["execution"]["mode"] == "scheduled"


class TestMetricsRecording:
    """Tests for Prometheus metrics recording."""

    async def test_records_success_metrics(self) -> None:
        """Should record SCHEDULED_TRIGGER_FIRES and SCHEDULED_TRIGGER_LATENCY on success."""
        launcher = _make_launcher()
        workflow_id_str = str(uuid4())
        scheduled_at = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        triggered_at = scheduled_at + timedelta(seconds=5)

        mock_info = _make_mock_activity_info(scheduled_at, triggered_at)
        mock_recorder = MagicMock()

        with (
            patch("syntara.workflows.workflow_engine.scheduled_launcher.activity") as mock_activity,
            patch(
                "syntara.workflows.workflow_engine.scheduled_launcher.get_metrics_recorder", return_value=mock_recorder
            ),
            patch.object(launcher, "_create_execution", new_callable=AsyncMock) as mock_create,
        ):
            mock_activity.info.return_value = mock_info
            mock_create.return_value = {"execution_id": "exec-1", "temporal_workflow_id": "tw-1"}

            launcher._session_factory = MagicMock()
            launcher._session_factory.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            launcher._session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            await launcher.run(workflow_id_str, "trigger_1")

        calls = mock_recorder.record.call_args_list
        assert len(calls) == 2

        fires_call = calls[0]
        assert fires_call[0][0] == MetricType.SCHEDULED_TRIGGER_FIRES
        assert fires_call[1]["labels"]["status"] == "success"

        latency_call = calls[1]
        assert latency_call[0][0] == MetricType.SCHEDULED_TRIGGER_LATENCY
        assert latency_call[1]["value"] == pytest.approx(5000.0)

    async def test_records_error_metrics_on_failure(self) -> None:
        """Should record SCHEDULED_TRIGGER_FIRES with status=error on failure."""
        launcher = _make_launcher()
        workflow_id_str = str(uuid4())
        scheduled_at = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        triggered_at = scheduled_at + timedelta(seconds=2)

        mock_info = _make_mock_activity_info(scheduled_at, triggered_at)
        mock_recorder = MagicMock()

        with (
            patch("syntara.workflows.workflow_engine.scheduled_launcher.activity") as mock_activity,
            patch(
                "syntara.workflows.workflow_engine.scheduled_launcher.get_metrics_recorder", return_value=mock_recorder
            ),
            patch.object(launcher, "_create_execution", new_callable=AsyncMock) as mock_create,
        ):
            mock_activity.info.return_value = mock_info
            mock_create.side_effect = RuntimeError("Workflow not published")

            launcher._session_factory = MagicMock()
            launcher._session_factory.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            launcher._session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(RuntimeError, match="Workflow not published"):
                await launcher.run(workflow_id_str, "trigger_1")

        calls = mock_recorder.record.call_args_list
        assert len(calls) == 1
        error_call = calls[0]
        assert error_call[0][0] == MetricType.SCHEDULED_TRIGGER_FIRES
        assert error_call[1]["labels"]["status"] == "error"

    async def test_metrics_error_does_not_swallow_original_exception(self) -> None:
        """If recorder.record() fails on the error path, the original exception should still propagate."""
        launcher = _make_launcher()
        workflow_id_str = str(uuid4())
        scheduled_at = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        triggered_at = scheduled_at + timedelta(seconds=2)

        mock_info = _make_mock_activity_info(scheduled_at, triggered_at)
        mock_recorder = MagicMock()
        mock_recorder.record.side_effect = RuntimeError("metrics broken")

        with (
            patch("syntara.workflows.workflow_engine.scheduled_launcher.activity") as mock_activity,
            patch(
                "syntara.workflows.workflow_engine.scheduled_launcher.get_metrics_recorder", return_value=mock_recorder
            ),
            patch.object(launcher, "_create_execution", new_callable=AsyncMock) as mock_create,
        ):
            mock_activity.info.return_value = mock_info
            mock_create.side_effect = ValueError("workflow not found")

            launcher._session_factory = MagicMock()
            launcher._session_factory.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
            launcher._session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ValueError, match="workflow not found"):
                await launcher.run(workflow_id_str, "trigger_1")


class TestSetupActivityNoTemporalStart:
    """Tests that the setup activity does NOT start workflows via TemporalExecutionService.

    After the child-workflow refactor (AAP-82536), the activity only handles
    DB operations. Starting OrchestratorWorkflow is the launcher workflow's
    responsibility via execute_child_workflow.
    """

    def test_setup_does_not_import_temporal_execution_service(self) -> None:
        """The scheduled launcher module must NOT import TemporalExecutionService."""
        import syntara.workflows.workflow_engine.scheduled_launcher as launcher_module

        assert not hasattr(launcher_module, "create_temporal_execution_service")

    async def test_setup_returns_child_workflow_data(self) -> None:
        """The setup activity result must include all data needed for child workflow start."""
        launcher = _make_launcher()
        workflow_id = uuid4()
        scheduled_at = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        triggered_at = datetime(2024, 1, 1, 9, 0, 3, tzinfo=UTC)
        workflow_def = {
            "schema_version": "2.0.0",
            "triggers": [],
            "nodes": [],
            "edges": [],
        }

        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.name = "test-workflow"
        mock_workflow.project_id = uuid4()
        mock_workflow.created_by = uuid4()
        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.workflow_definition = workflow_def

        with (
            patch.object(launcher, "_load_published_workflow", return_value=(mock_workflow, mock_version)),
            patch("syntara.workflows.workflow_engine.scheduled_launcher.get_settings") as mock_get_settings,
            patch(
                "syntara.workflows.workflow_engine.scheduled_launcher.resolve_user_display_name",
                return_value="Author Name",
            ),
        ):
            mock_get_settings.return_value.service_identity = "backend.ao.svc"
            mock_get_settings.return_value.max_concurrent_workflows = 0

            mock_session = AsyncMock()
            launcher._session_factory = MagicMock()
            launcher._session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            launcher._session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await launcher._create_execution(workflow_id, "trigger_1", scheduled_at, triggered_at)

        assert "execution_id" in result
        assert "temporal_workflow_id" in result
        assert "workflow_definition" in result
        assert result["workflow_definition"] == workflow_def
        assert "trigger_node_id" in result
        assert result["trigger_node_id"] == "trigger_1"
        assert "input_data" in result
        assert "task_queue" in result
        assert result["task_queue"] == "test-queue"
        assert "workflow_metadata" in result

    async def test_setup_generates_temporal_workflow_id_directly(self) -> None:
        """The temporal_workflow_id must be generated as {name}-{execution_id} without TemporalExecutionService."""
        launcher = _make_launcher()
        workflow_id = uuid4()
        scheduled_at = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        triggered_at = datetime(2024, 1, 1, 9, 0, 3, tzinfo=UTC)

        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.name = "my-workflow"
        mock_workflow.project_id = uuid4()
        mock_workflow.created_by = uuid4()
        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "triggers": [],
            "nodes": [],
            "edges": [],
        }

        with (
            patch.object(launcher, "_load_published_workflow", return_value=(mock_workflow, mock_version)),
            patch("syntara.workflows.workflow_engine.scheduled_launcher.get_settings") as mock_get_settings,
            patch(
                "syntara.workflows.workflow_engine.scheduled_launcher.resolve_user_display_name",
                return_value="Author Name",
            ),
        ):
            mock_get_settings.return_value.service_identity = "backend.ao.svc"
            mock_get_settings.return_value.max_concurrent_workflows = 0

            mock_session = AsyncMock()
            launcher._session_factory = MagicMock()
            launcher._session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            launcher._session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await launcher._create_execution(workflow_id, "trigger_1", scheduled_at, triggered_at)

        execution_id = result["execution_id"]
        expected_temporal_id = f"my-workflow-{execution_id}"
        assert result["temporal_workflow_id"] == expected_temporal_id


class TestScheduledLauncherConcurrencyLimit:
    """Tests for the application-level concurrency gate in ScheduledExecutionLauncher."""

    async def test_raises_when_active_meets_limit(self) -> None:
        """_create_execution raises non-retryable ApplicationError when active >= limit."""
        from temporalio.exceptions import ApplicationError

        launcher = _make_launcher()
        workflow_id = uuid4()
        scheduled_at = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        triggered_at = datetime(2024, 1, 1, 9, 0, 3, tzinfo=UTC)

        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.name = "test-workflow"
        mock_workflow.project_id = uuid4()
        mock_workflow.created_by = uuid4()
        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "triggers": [],
            "nodes": [],
            "edges": [],
        }

        with (
            patch.object(launcher, "_load_published_workflow", return_value=(mock_workflow, mock_version)),
            patch("syntara.workflows.workflow_engine.scheduled_launcher.get_settings") as mock_get_settings,
            patch(
                "syntara.workflows.workflow_engine.scheduled_launcher.resolve_user_display_name",
                return_value="Author Name",
            ),
            patch(
                "syntara.workflows.services.execution_service.count_active_executions",
                new_callable=AsyncMock,
                return_value=5,
            ) as mock_count,
        ):
            mock_get_settings.return_value.service_identity = "backend.ao.svc"
            mock_get_settings.return_value.max_concurrent_workflows = 5

            mock_session = AsyncMock()
            launcher._session_factory = MagicMock()
            launcher._session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            launcher._session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(ApplicationError, match="concurrency limit reached") as exc_info:
                await launcher._create_execution(workflow_id, "trigger_1", scheduled_at, triggered_at)

        assert exc_info.value.non_retryable is True
        mock_count.assert_awaited_once_with(mock_session)
        mock_session.add.assert_not_called()

    async def test_proceeds_when_under_limit(self) -> None:
        """_create_execution continues when active count is below the configured limit."""
        launcher = _make_launcher()
        workflow_id = uuid4()
        scheduled_at = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        triggered_at = datetime(2024, 1, 1, 9, 0, 3, tzinfo=UTC)

        mock_workflow = MagicMock()
        mock_workflow.id = workflow_id
        mock_workflow.name = "test-workflow"
        mock_workflow.project_id = uuid4()
        mock_workflow.created_by = uuid4()
        mock_version = MagicMock()
        mock_version.id = uuid4()
        mock_version.version = 1
        mock_version.workflow_definition = {
            "schema_version": "2.0.0",
            "triggers": [],
            "nodes": [],
            "edges": [],
        }

        with (
            patch.object(launcher, "_load_published_workflow", return_value=(mock_workflow, mock_version)),
            patch("syntara.workflows.workflow_engine.scheduled_launcher.get_settings") as mock_get_settings,
            patch(
                "syntara.workflows.workflow_engine.scheduled_launcher.resolve_user_display_name",
                return_value="Author Name",
            ),
            patch(
                "syntara.workflows.services.execution_service.count_active_executions",
                new_callable=AsyncMock,
                return_value=2,
            ) as mock_count,
        ):
            mock_get_settings.return_value.service_identity = "backend.ao.svc"
            mock_get_settings.return_value.max_concurrent_workflows = 5

            mock_session = AsyncMock()
            launcher._session_factory = MagicMock()
            launcher._session_factory.return_value.__aenter__ = AsyncMock(return_value=mock_session)
            launcher._session_factory.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await launcher._create_execution(workflow_id, "trigger_1", scheduled_at, triggered_at)

        mock_count.assert_awaited_once_with(mock_session)
        mock_session.add.assert_called_once()
        assert "execution_id" in result


class TestLauncherWorkflow:
    """Tests for the ScheduledWorkflowLauncher workflow."""

    async def test_run_starts_child_workflow_with_correct_args(self) -> None:
        """The launcher must call execute_child_workflow with the setup activity result."""
        from syntara.workflows.workflow_engine.scheduled_launcher import ScheduledWorkflowLauncher

        setup_data = {
            "execution_id": "exec-123",
            "temporal_workflow_id": "wf-exec-123",
            "workflow_definition": {"schema_version": "2.0.0", "triggers": [], "nodes": [], "edges": []},
            "trigger_node_id": "trigger_1",
            "input_data": {"scheduled_at": "2024-01-01T09:00:00", "triggered_at": "2024-01-01T09:00:03"},
            "task_queue": "test-queue",
            "workflow_metadata": {"workflow_context": {}},
        }

        launcher = ScheduledWorkflowLauncher()

        with (
            patch("temporalio.workflow.execute_activity", new_callable=AsyncMock, return_value=setup_data),
            patch("temporalio.workflow.execute_child_workflow", new_callable=AsyncMock) as mock_child,
        ):
            result = await launcher.run("wf-id", "trigger_1")

        mock_child.assert_called_once()
        call_kwargs = mock_child.call_args
        assert call_kwargs[0][0] == "orchestrator_workflow"
        assert call_kwargs[1]["id"] == "wf-exec-123"
        assert call_kwargs[1]["task_queue"] == "test-queue"
        assert result == {"execution_id": "exec-123", "temporal_workflow_id": "wf-exec-123"}

    async def test_run_uses_request_cancel_parent_close_policy(self) -> None:
        """Child workflow must use REQUEST_CANCEL so cancel_other works correctly."""
        from temporalio.workflow import ParentClosePolicy

        from syntara.workflows.workflow_engine.scheduled_launcher import ScheduledWorkflowLauncher

        setup_data = {
            "execution_id": "exec-123",
            "temporal_workflow_id": "wf-exec-123",
            "workflow_definition": {},
            "trigger_node_id": "trigger_1",
            "input_data": {},
            "task_queue": "test-queue",
            "workflow_metadata": {},
        }

        launcher = ScheduledWorkflowLauncher()

        with (
            patch("temporalio.workflow.execute_activity", new_callable=AsyncMock, return_value=setup_data),
            patch("temporalio.workflow.execute_child_workflow", new_callable=AsyncMock) as mock_child,
        ):
            await launcher.run("wf-id", "trigger_1")

        assert mock_child.call_args[1]["parent_close_policy"] == ParentClosePolicy.REQUEST_CANCEL


class TestActivityRegistration:
    """Guards against regressions in activity naming and launcher architecture."""

    def test_activity_name_is_setup(self) -> None:
        """Activity must be named 'setup_scheduled_execution'.

        The old name 'launch_scheduled_execution' reflected the fire-and-forget
        pattern where the activity started OrchestratorWorkflow. After the child-workflow
        refactor (AAP-82536), the activity only sets up DB records.
        """
        from syntara.workflows.workflow_engine.scheduled_launcher import _LAUNCHER_ACTIVITY_NAME

        assert _LAUNCHER_ACTIVITY_NAME == "setup_scheduled_execution"

    def test_launcher_workflow_name_unchanged(self) -> None:
        """The Temporal workflow name must stay 'scheduled_workflow_launcher'.

        Temporal Schedules reference this name in their action config. Changing
        it would break all existing schedules.
        """
        from syntara.workflows.workflow_engine.scheduled_launcher import ScheduledWorkflowLauncher

        defn = getattr(ScheduledWorkflowLauncher, "__temporal_workflow_definition")
        assert defn.name == "scheduled_workflow_launcher"


class TestLoadPublishedWorkflow:
    """Tests for _load_published_workflow static method."""

    async def test_returns_workflow_and_version(self) -> None:
        """Should return (Workflow, WorkflowVersion) tuple when found."""
        mock_workflow = MagicMock()
        mock_version = MagicMock()

        mock_result = MagicMock()
        mock_result.first.return_value = (mock_workflow, mock_version)

        session = AsyncMock()
        session.exec.return_value = mock_result

        wf, ver = await ScheduledExecutionLauncher._load_published_workflow(session, uuid4())
        assert wf is mock_workflow
        assert ver is mock_version

    async def test_raises_when_not_found(self) -> None:
        """Should raise WorkflowNotPublishedError when workflow is missing, deleted, or disabled."""
        mock_result = MagicMock()
        mock_result.first.return_value = None

        session = AsyncMock()
        session.exec.return_value = mock_result

        with pytest.raises(WorkflowNotPublishedError):
            await ScheduledExecutionLauncher._load_published_workflow(session, uuid4())


class TestNonRetryablePermanentFailures:
    """Tests that permanent failures are raised as non-retryable ApplicationErrors (AAP-86776).

    A schedule firing against a workflow that is missing, soft-deleted,
    disabled, or unpublished must fail once — not retry forever under
    Temporal's default unlimited retry policy.
    """

    async def test_workflow_not_published_raises_non_retryable_application_error(self) -> None:
        """WorkflowNotPublishedError must surface as ApplicationError(non_retryable=True)."""
        launcher = _make_launcher()
        workflow_id = uuid4()
        workflow_id_str = str(workflow_id)
        scheduled_at = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        triggered_at = scheduled_at + timedelta(seconds=3)

        mock_info = _make_mock_activity_info(scheduled_at, triggered_at)
        mock_recorder = MagicMock()

        with (
            patch("syntara.workflows.workflow_engine.scheduled_launcher.activity") as mock_activity,
            patch(
                "syntara.workflows.workflow_engine.scheduled_launcher.get_metrics_recorder", return_value=mock_recorder
            ),
            patch.object(
                launcher,
                "_create_execution",
                new_callable=AsyncMock,
                side_effect=WorkflowNotPublishedError(workflow_id),
            ),
        ):
            mock_activity.info.return_value = mock_info

            with pytest.raises(ApplicationError, match="has no published version") as exc_info:
                await launcher.run(workflow_id_str, "trigger_1")

            assert exc_info.value.non_retryable is True
            assert exc_info.value.type == "WorkflowNotPublishedError"

        # Error metric should still be recorded
        calls = mock_recorder.record.call_args_list
        assert len(calls) == 1
        assert calls[0][1]["labels"]["status"] == "error"

    async def test_transient_error_remains_retryable(self) -> None:
        """A transient error (e.g. DB connection lost) must NOT be wrapped as non-retryable."""
        launcher = _make_launcher()
        workflow_id_str = str(uuid4())
        scheduled_at = datetime(2024, 1, 1, 9, 0, 0, tzinfo=UTC)
        triggered_at = scheduled_at + timedelta(seconds=2)

        mock_info = _make_mock_activity_info(scheduled_at, triggered_at)
        mock_recorder = MagicMock()

        with (
            patch("syntara.workflows.workflow_engine.scheduled_launcher.activity") as mock_activity,
            patch(
                "syntara.workflows.workflow_engine.scheduled_launcher.get_metrics_recorder", return_value=mock_recorder
            ),
            patch.object(
                launcher,
                "_create_execution",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB connection lost"),
            ),
        ):
            mock_activity.info.return_value = mock_info

            with pytest.raises(RuntimeError, match="DB connection lost"):
                await launcher.run(workflow_id_str, "trigger_1")
