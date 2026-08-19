"""Integration tests for workflow metrics instrumentation (FR-014 to FR-017).

Uses real database fixtures to validate that ``ExecutionService`` emits the
expected metrics records when encountering terminal executions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from prometheus_client import CollectorRegistry

from syntara.core.models import User
from syntara.metrics.emission import reset_emission_trackers
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import MetricType
from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus
from syntara.workflows.services.execution_service import ExecutionService

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

    from tests.integration.helpers.workflow import ActivitiesFactory, ExecutionsFactory

PATCH_TARGET = "syntara.workflows.services.execution_service.get_metrics_recorder"


@pytest.fixture
def recorder() -> MetricsRecorder:
    """Fresh MetricsRecorder with an isolated Prometheus registry."""
    return MetricsRecorder(
        retention_seconds=3600,
        max_records=10_000,
        prometheus_registry=CollectorRegistry(),
    )


@pytest_asyncio.fixture
async def completed_execution(
    executions_factory: ExecutionsFactory,
    test_db_session: AsyncSession,
) -> Execution:
    """A single COMPLETED execution with ``completed_at`` set."""
    execs = await executions_factory.create_executions(count=1, status=ExecutionStatus.COMPLETED)
    execution = execs[0]
    execution.completed_at = datetime.now(UTC)
    test_db_session.add(execution)
    await test_db_session.commit()
    await test_db_session.refresh(execution)
    return execution


@pytest_asyncio.fixture
async def failed_execution(
    executions_factory: ExecutionsFactory,
    test_db_session: AsyncSession,
) -> Execution:
    """A single FAILED execution with ``completed_at`` set."""
    execs = await executions_factory.create_executions(count=1, status=ExecutionStatus.FAILED)
    execution = execs[0]
    execution.completed_at = datetime.now(UTC)
    test_db_session.add(execution)
    await test_db_session.commit()
    await test_db_session.refresh(execution)
    return execution


def _make_service(session: AsyncSession) -> ExecutionService:
    user = MagicMock(spec=User)
    return ExecutionService(session, user, temporal_service=None)


# =============================================================================
# Workflow completion metrics
# =============================================================================


class TestWorkflowCompletionMetrics:
    """Tests for workflow-level metrics emitted by _emit_completion_metrics."""

    def setup_method(self) -> None:
        reset_emission_trackers()

    @pytest.mark.asyncio
    async def test_records_duration_with_workflow_type(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        test_db_session: AsyncSession,
    ) -> None:
        service = _make_service(test_db_session)

        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)

        results = list(recorder.query(metric_types={MetricType.WORKFLOW_DURATION}))
        assert len(results) == 1
        assert results[0].labels["status"] == "completed"
        assert results[0].labels["workflow_type"] == "test-workflow"
        assert results[0].labels["execution_id"] == str(completed_execution.id)
        assert results[0].value > 0

    @pytest.mark.asyncio
    async def test_records_status_for_failed_execution(
        self,
        recorder: MetricsRecorder,
        failed_execution: Execution,
        test_db_session: AsyncSession,
    ) -> None:
        service = _make_service(test_db_session)

        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(failed_execution)

        results = list(recorder.query(metric_types={MetricType.WORKFLOW_STATUS}))
        assert len(results) == 1
        assert results[0].labels["status"] == "failed"

    @pytest.mark.asyncio
    async def test_skips_non_terminal_execution(
        self,
        recorder: MetricsRecorder,
        executions_factory: ExecutionsFactory,
        test_db_session: AsyncSession,
    ) -> None:
        execs = await executions_factory.create_executions(count=1, status=ExecutionStatus.RUNNING)
        service = _make_service(test_db_session)

        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(execs[0])

        assert len(list(recorder.query(metric_types={MetricType.WORKFLOW_DURATION}))) == 0

    @pytest.mark.asyncio
    async def test_idempotent_emission(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        test_db_session: AsyncSession,
    ) -> None:
        service = _make_service(test_db_session)

        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)
            await service._emit_completion_metrics(completed_execution)

        assert len(list(recorder.query(metric_types={MetricType.WORKFLOW_DURATION}))) == 1

    @pytest.mark.asyncio
    async def test_observes_prometheus_histogram(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        test_db_session: AsyncSession,
    ) -> None:
        service = _make_service(test_db_session)

        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)

        assert recorder.prometheus.workflow_duration_seconds._sum.get() > 0


# =============================================================================
# Per-activity duration metrics
# =============================================================================


class TestActivityDurationMetrics:
    """Tests for activity-level metrics emitted alongside workflow completion."""

    def setup_method(self) -> None:
        reset_emission_trackers()

    @pytest.mark.asyncio
    async def test_records_durations_with_workflow_type(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await activities_factory.create_activities(completed_execution, ["step-one", "step-two"], duration_seconds=2.0)

        service = _make_service(test_db_session)
        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)

        results = list(recorder.query(metric_types={MetricType.ACTIVITY_DURATION}))
        assert len(results) == 2
        names = {r.labels["activity_name"] for r in results}
        assert names == {"step-one", "step-two"}
        for r in results:
            assert r.labels["workflow_type"] == "test-workflow"

    @pytest.mark.asyncio
    async def test_skips_running_activities(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await activities_factory.create_activities(completed_execution, ["in-progress"], status=ActivityStatus.RUNNING)

        service = _make_service(test_db_session)
        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)

        assert len(list(recorder.query(metric_types={MetricType.ACTIVITY_DURATION}))) == 0

    @pytest.mark.asyncio
    async def test_idempotent_activity_emission(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await activities_factory.create_activities(completed_execution, ["step-one"])

        service = _make_service(test_db_session)
        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)
            await service._emit_completion_metrics(completed_execution)

        assert len(list(recorder.query(metric_types={MetricType.ACTIVITY_DURATION}))) == 1

    @pytest.mark.asyncio
    async def test_observes_prometheus_histogram(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await activities_factory.create_activities(completed_execution, ["say_hello"], duration_seconds=1.5)

        service = _make_service(test_db_session)
        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)

        assert (
            recorder.prometheus.activity_duration_seconds.labels(
                activity_name="say_hello",
                status="completed",
                workflow_type="test-workflow",
            )._sum.get()
            > 0
        )


# =============================================================================
# Activity duration Prometheus labels
# =============================================================================


class TestActivityDurationPrometheusLabels:
    """Tests that ACTIVITY_DURATION Prometheus histogram carries the correct labels."""

    def setup_method(self) -> None:
        reset_emission_trackers()

    @pytest.mark.asyncio
    async def test_prometheus_labels_match_activity(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await activities_factory.create_activities(completed_execution, ["fetch_data"], duration_seconds=2.0)

        service = _make_service(test_db_session)
        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)

        labeled = recorder.prometheus.activity_duration_seconds.labels(
            activity_name="fetch_data",
            status="completed",
            workflow_type="test-workflow",
        )
        assert labeled._sum.get() > 0

    @pytest.mark.asyncio
    async def test_failed_activity_gets_failed_label(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await activities_factory.create_activities(
            completed_execution,
            ["bad_step"],
            status=ActivityStatus.FAILED,
            duration_seconds=0.5,
        )

        service = _make_service(test_db_session)
        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)

        labeled = recorder.prometheus.activity_duration_seconds.labels(
            activity_name="bad_step",
            status="failed",
            workflow_type="test-workflow",
        )
        assert labeled._sum.get() > 0


# =============================================================================
# Activity execution success rate
# =============================================================================


class TestActivityExecutionSuccessRate:
    """Tests for ACTIVITY_EXECUTION_SUCCESS_RATE emitted after activity processing."""

    def setup_method(self) -> None:
        reset_emission_trackers()

    @pytest.mark.asyncio
    async def test_all_succeeded_yields_rate_one(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await activities_factory.create_activities(completed_execution, ["a", "b", "c"])

        service = _make_service(test_db_session)
        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)

        results = list(recorder.query(metric_types={MetricType.ACTIVITY_EXECUTION_SUCCESS_RATE}))
        assert len(results) == 1
        assert results[0].value == pytest.approx(1.0)
        assert results[0].labels["component"] == "temporal_worker"

    @pytest.mark.asyncio
    async def test_mixed_results_yields_correct_ratio(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await activities_factory.create_activities(completed_execution, ["ok1", "ok2"])
        await activities_factory.create_activities(
            completed_execution,
            ["fail1"],
            status=ActivityStatus.FAILED,
        )

        service = _make_service(test_db_session)
        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)

        results = list(recorder.query(metric_types={MetricType.ACTIVITY_EXECUTION_SUCCESS_RATE}))
        assert len(results) == 1
        assert results[0].value == pytest.approx(2.0 / 3.0)

    @pytest.mark.asyncio
    async def test_no_terminal_activities_skips_recording(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await activities_factory.create_activities(
            completed_execution,
            ["running"],
            status=ActivityStatus.RUNNING,
        )

        service = _make_service(test_db_session)
        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)

        results = list(recorder.query(metric_types={MetricType.ACTIVITY_EXECUTION_SUCCESS_RATE}))
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_updates_prometheus_gauge(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await activities_factory.create_activities(completed_execution, ["step"])

        service = _make_service(test_db_session)
        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)

        gauge_value = recorder.prometheus.activity_execution_success_rate.labels(
            component="temporal_worker",
        )._value.get()
        assert gauge_value == pytest.approx(1.0)


# =============================================================================
# Workflow completion rate
# =============================================================================


class TestWorkflowCompletionRate:
    """Tests for WORKFLOW_COMPLETION_RATE emitted on terminal workflow state."""

    def setup_method(self) -> None:
        reset_emission_trackers()

    @pytest.mark.asyncio
    async def test_completed_execution_records_rate_one(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        test_db_session: AsyncSession,
    ) -> None:
        service = _make_service(test_db_session)
        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)

        results = list(recorder.query(metric_types={MetricType.WORKFLOW_COMPLETION_RATE}))
        assert len(results) == 1
        assert results[0].value == pytest.approx(1.0)
        assert results[0].labels["component"] == "execution_service"

    @pytest.mark.asyncio
    async def test_failed_execution_records_rate_zero(
        self,
        recorder: MetricsRecorder,
        failed_execution: Execution,
        test_db_session: AsyncSession,
    ) -> None:
        service = _make_service(test_db_session)
        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(failed_execution)

        results = list(recorder.query(metric_types={MetricType.WORKFLOW_COMPLETION_RATE}))
        assert len(results) == 1
        assert results[0].value == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_updates_prometheus_gauge(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        test_db_session: AsyncSession,
    ) -> None:
        service = _make_service(test_db_session)
        with patch(PATCH_TARGET, return_value=recorder):
            await service._emit_completion_metrics(completed_execution)

        gauge_value = recorder.prometheus.workflow_completion_rate.labels(
            component="execution_service",
        )._value.get()
        assert gauge_value == pytest.approx(1.0)
