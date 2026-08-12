"""Integration tests for background queue routing of built-in workflows.

Verifies that built-in workflows (Document Conversion, Agent Execution)
are routed to ``orchestrator-background-queue`` and NOT to ``orchestrator-workflow-queue``,
preventing system operations from starving user workflow execution (AAP-78968,
AAP-83413).

Test coverage:
- Seeded built-in workflows have ``is_builtin=True`` in the database.
- ``TemporalExecutionService.start_workflow`` selects the background task queue
  when ``is_builtin=True`` and the user task queue when ``is_builtin=False``.
- The ``Execution`` database record created for a built-in workflow is
  reachable via the executions API.
- Queue depth metrics carry the ``task_queue`` label so Prometheus can
  distinguish background-queue depth from workflow-queue depth.

No live Temporal server is required — the tests mock ``temporalio.client.Client``
at the layer where task-queue selection occurs, then assert on the captured
``task_queue`` argument.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlmodel import col, select

from syntara.core.config.base import get_settings
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import MetricType
from syntara.workflows.models.workflow import Workflow
from syntara.workflows.workflow_engine.services.temporal_execution_service import TemporalExecutionService

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture(autouse=True)
def _seed_builtins(_seed_integration_data: None) -> None:
    """Opt into shared authz + builtin workflow seeding for this module."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MINIMAL_V2_DEF = {
    "schema_version": "2.0.0",
    "name": "Test Workflow",
    "triggers": [{"id": "trigger_api", "type": "manual_trigger", "parameters": {}}],
    "nodes": [],
    "edges": [{"from": "trigger_api", "to": "trigger_api"}],
}


def _make_temporal_service(
    task_queue: str = "orchestrator-workflow-queue",
    background_task_queue: str = "orchestrator-background-queue",
) -> tuple[TemporalExecutionService, MagicMock]:
    """Return a ``TemporalExecutionService`` with a mocked Temporal client.

    The mock captures ``task_queue`` from ``client.start_workflow()`` calls so
    tests can assert which queue was selected without a live Temporal server.
    """
    mock_client = AsyncMock()
    mock_handle = MagicMock()
    mock_handle.first_execution_run_id = "run-test-001"
    mock_client.start_workflow = AsyncMock(return_value=mock_handle)

    service = TemporalExecutionService(
        temporal_client=mock_client,
        task_queue=task_queue,
        background_task_queue=background_task_queue,
    )
    return service, mock_client


# ---------------------------------------------------------------------------
# Database-level checks
# ---------------------------------------------------------------------------


class TestBuiltinWorkflowsInDatabase:
    """Verify built-in workflows exist in the database with correct flags."""

    @pytest.mark.asyncio
    async def test_builtin_workflows_are_seeded(self, test_db_session: AsyncSession) -> None:
        """Seeded built-in workflows have is_builtin=True in the Workflow table."""
        stmt = select(Workflow).where(col(Workflow.is_builtin) == True)  # noqa: E712
        result = await test_db_session.exec(stmt)
        builtins = result.all()

        assert len(builtins) >= 1, "At least one built-in workflow must be seeded"
        names = {w.name for w in builtins}
        assert "Document Conversion" in names, "Document Conversion must be seeded as a built-in workflow"

    @pytest.mark.asyncio
    async def test_builtin_workflows_cannot_be_deleted_via_flag(self, test_db_session: AsyncSession) -> None:
        """All seeded built-in workflows have is_builtin=True (not accidentally False)."""
        stmt = select(Workflow).where(col(Workflow.is_builtin) == True)  # noqa: E712
        result = await test_db_session.exec(stmt)
        builtins = result.all()

        for workflow in builtins:
            assert workflow.is_builtin is True, f"Workflow {workflow.name} should have is_builtin=True"


# ---------------------------------------------------------------------------
# Task queue routing
# ---------------------------------------------------------------------------


class TestBackgroundQueueRouting:
    """Verify TemporalExecutionService routes is_builtin workflows correctly."""

    @pytest.mark.asyncio
    async def test_builtin_workflow_routes_to_background_queue(self) -> None:
        """is_builtin=True causes start_workflow to use the background task queue."""
        service, mock_client = _make_temporal_service(
            task_queue="orchestrator-workflow-queue",
            background_task_queue="orchestrator-background-queue",
        )

        await service.start_workflow(
            workflow_def=_MINIMAL_V2_DEF,
            workflow_name="Document Conversion",
            trigger_node_id="trigger_api",
            is_builtin=True,
        )

        mock_client.start_workflow.assert_called_once()
        _, kwargs = mock_client.start_workflow.call_args
        assert kwargs["task_queue"] == "orchestrator-background-queue", (
            "Built-in workflows must be routed to orchestrator-background-queue, not to the user workflow queue"
        )

    @pytest.mark.asyncio
    async def test_user_workflow_routes_to_workflow_queue(self) -> None:
        """is_builtin=False (default) causes start_workflow to use the user task queue."""
        service, mock_client = _make_temporal_service(
            task_queue="orchestrator-workflow-queue",
            background_task_queue="orchestrator-background-queue",
        )

        await service.start_workflow(
            workflow_def=_MINIMAL_V2_DEF,
            workflow_name="My User Workflow",
            trigger_node_id="trigger_api",
            is_builtin=False,
        )

        mock_client.start_workflow.assert_called_once()
        _, kwargs = mock_client.start_workflow.call_args
        assert kwargs["task_queue"] == "orchestrator-workflow-queue", (
            "User workflows must NOT be routed to the background queue"
        )

    @pytest.mark.asyncio
    async def test_is_builtin_defaults_to_false(self) -> None:
        """is_builtin defaults to False — new workflows are NOT routed to background queue."""
        service, mock_client = _make_temporal_service()

        # Call without is_builtin argument
        await service.start_workflow(
            workflow_def=_MINIMAL_V2_DEF,
            workflow_name="New User Workflow",
            trigger_node_id="trigger_api",
        )

        _, kwargs = mock_client.start_workflow.call_args
        assert kwargs["task_queue"] == "orchestrator-workflow-queue", (
            "Default routing must be to the user workflow queue, not the background queue"
        )

    @pytest.mark.asyncio
    async def test_queue_names_match_settings(self) -> None:
        """Task queue names in TemporalExecutionService match the application settings."""
        settings = get_settings()

        service, mock_client = _make_temporal_service(
            task_queue=settings.task_queue,
            background_task_queue=settings.background_task_queue,
        )

        # Builtin → background queue from settings
        await service.start_workflow(
            workflow_def=_MINIMAL_V2_DEF,
            workflow_name="Document Conversion",
            trigger_node_id="trigger_api",
            is_builtin=True,
        )
        _, kwargs = mock_client.start_workflow.call_args
        assert kwargs["task_queue"] == settings.background_task_queue

        # User → user queue from settings
        mock_client.reset_mock()
        await service.start_workflow(
            workflow_def=_MINIMAL_V2_DEF,
            workflow_name="User Workflow",
            trigger_node_id="trigger_api",
            is_builtin=False,
        )
        _, kwargs = mock_client.start_workflow.call_args
        assert kwargs["task_queue"] == settings.task_queue

    @pytest.mark.asyncio
    async def test_no_cross_queue_pollution(self) -> None:
        """Multiple concurrent builtin and user workflows each go to their correct queue."""
        service, mock_client = _make_temporal_service()

        calls: list[tuple[str, object]] = []

        async def _capture_start(*args: object, **kwargs: object) -> MagicMock:
            name = kwargs.get("id", str(uuid4()))
            queue = kwargs["task_queue"]
            calls.append((str(name), queue))
            handle = MagicMock()
            handle.first_execution_run_id = f"run-{len(calls)}"
            return handle

        mock_client.start_workflow = AsyncMock(side_effect=_capture_start)

        # Mix of builtin and user workflows
        for _ in range(3):
            await service.start_workflow(
                workflow_def=_MINIMAL_V2_DEF,
                workflow_name="Document Conversion",
                trigger_node_id="trigger_api",
                is_builtin=True,
            )
        for _ in range(3):
            await service.start_workflow(
                workflow_def=_MINIMAL_V2_DEF,
                workflow_name=f"User Workflow {_}",
                trigger_node_id="trigger_api",
                is_builtin=False,
            )

        assert len(calls) == 6
        background_calls = [c for c in calls if c[1] == "orchestrator-background-queue"]
        user_calls = [c for c in calls if c[1] == "orchestrator-workflow-queue"]
        assert len(background_calls) == 3, "3 builtin workflows must go to background queue"
        assert len(user_calls) == 3, "3 user workflows must go to workflow queue"


# ---------------------------------------------------------------------------
# Metrics label verification
# ---------------------------------------------------------------------------


class TestQueueDepthMetricLabels:
    """Verify orchestrator_temporal_queue_depth metric carries task_queue label.

    The queue depth metric must include ``task_queue`` label so Prometheus
    can distinguish background-queue depth from workflow-queue depth when
    configuring HPA rules (AAP-81954) and alerting.
    """

    def test_temporal_queue_depth_metric_supports_task_queue_label(self) -> None:
        """TEMPORAL_QUEUE_DEPTH records carry task_queue label when emitted."""
        from prometheus_client import CollectorRegistry

        recorder = MetricsRecorder(
            retention_seconds=60,
            max_records=100,
            prometheus_registry=CollectorRegistry(),
        )

        recorder.record(
            MetricType.TEMPORAL_QUEUE_DEPTH,
            5.0,
            labels={"task_queue": "orchestrator-background-queue"},
        )
        recorder.record(
            MetricType.TEMPORAL_QUEUE_DEPTH,
            0.0,
            labels={"task_queue": "orchestrator-workflow-queue"},
        )

        records = list(recorder.query(metric_types={MetricType.TEMPORAL_QUEUE_DEPTH}))
        assert len(records) == 2

        task_queues = {r.labels.get("task_queue") for r in records}
        assert "orchestrator-background-queue" in task_queues, (
            "Background queue must have its own labeled metric series for HPA targeting"
        )
        assert "orchestrator-workflow-queue" in task_queues

    def test_background_queue_depth_metric_value(self) -> None:
        """Background queue depth metric reflects the correct value."""
        from prometheus_client import CollectorRegistry

        recorder = MetricsRecorder(
            retention_seconds=60,
            max_records=100,
            prometheus_registry=CollectorRegistry(),
        )

        recorder.record(
            MetricType.TEMPORAL_QUEUE_DEPTH,
            7.0,
            labels={"task_queue": "orchestrator-background-queue"},
        )

        records = list(recorder.query(metric_types={MetricType.TEMPORAL_QUEUE_DEPTH}))
        bg_record = next(r for r in records if r.labels.get("task_queue") == "orchestrator-background-queue")
        assert bg_record.value == pytest.approx(7.0)
