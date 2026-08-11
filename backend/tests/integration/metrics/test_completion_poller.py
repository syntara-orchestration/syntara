"""Integration tests for the background completion-metrics poller.

These tests use a real database (via ``test_db_session``) and the
``executions_factory`` / ``activities_factory`` fixtures so that SQL
queries in ``poll_completed_executions`` are exercised end-to-end.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import patch
from uuid import uuid4

import pytest
import pytest_asyncio
from prometheus_client import CollectorRegistry
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.metrics.completion_poller import poll_completed_executions
from syntara.metrics.emission import emit_completion_metrics, emitted_completions, reset_emission_trackers
from syntara.metrics.recorder import MetricsRecorder
from syntara.metrics.types import MetricType
from syntara.workflows.models.activity_execution import ActivityStatus
from syntara.workflows.models.execution import Execution, ExecutionStatus

if TYPE_CHECKING:
    from syntara.workflows.models.workflow import Workflow
    from tests.integration.helpers.workflow import ActivitiesFactory, ExecutionsFactory


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
    test_workflow: Workflow,
) -> Execution:
    """Create a single completed execution with ``completed_at`` set."""
    execs = await executions_factory.create_executions(count=1, status=ExecutionStatus.COMPLETED)
    execution = execs[0]
    execution.completed_at = datetime.now(UTC)
    test_db_session.add(execution)
    await test_db_session.commit()
    await test_db_session.refresh(execution)
    return execution


# ---------------------------------------------------------------------------
# emit_completion_metrics (unified entry point)
# ---------------------------------------------------------------------------


class TestEmitCompletionMetrics:
    """Tests for the shared ``emit_completion_metrics`` helper."""

    def setup_method(self) -> None:
        reset_emission_trackers()

    @pytest.mark.asyncio
    async def test_emits_workflow_duration_and_status(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        test_db_session: AsyncSession,
    ) -> None:
        result = await emit_completion_metrics(test_db_session, completed_execution, recorder)
        assert result is True

        durations = list(recorder.query(metric_types={MetricType.WORKFLOW_DURATION}))
        assert len(durations) == 1
        assert durations[0].labels["workflow_type"] == "test-workflow"
        assert durations[0].value > 0

        statuses = list(recorder.query(metric_types={MetricType.WORKFLOW_STATUS}))
        assert len(statuses) == 1
        assert statuses[0].labels["status"] == "completed"

    @pytest.mark.asyncio
    async def test_emits_activity_durations(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await activities_factory.create_activities(completed_execution, ["step-a", "step-b"], duration_seconds=1.0)

        await emit_completion_metrics(test_db_session, completed_execution, recorder)

        results = list(recorder.query(metric_types={MetricType.ACTIVITY_DURATION}))
        assert len(results) == 2
        names = {r.labels["activity_name"] for r in results}
        assert names == {"step-a", "step-b"}

    @pytest.mark.asyncio
    async def test_skips_running_activity(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await activities_factory.create_activities(completed_execution, ["running-step"], status=ActivityStatus.RUNNING)

        await emit_completion_metrics(test_db_session, completed_execution, recorder)

        assert len(list(recorder.query(metric_types={MetricType.ACTIVITY_DURATION}))) == 0

    @pytest.mark.asyncio
    async def test_handles_skipped_activity(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        """SKIPPED activities should be emitted (terminal status)."""
        await activities_factory.create_activities(completed_execution, ["skipped-step"], status=ActivityStatus.SKIPPED)

        await emit_completion_metrics(test_db_session, completed_execution, recorder)

        results = list(recorder.query(metric_types={MetricType.ACTIVITY_DURATION}))
        assert len(results) == 1
        assert results[0].labels["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_skips_non_terminal_execution(
        self,
        recorder: MetricsRecorder,
        executions_factory: ExecutionsFactory,
        test_db_session: AsyncSession,
    ) -> None:
        execs = await executions_factory.create_executions(count=1, status=ExecutionStatus.RUNNING)

        result = await emit_completion_metrics(test_db_session, execs[0], recorder)
        assert result is False

        assert len(list(recorder.query(metric_types={MetricType.WORKFLOW_DURATION}))) == 0

    @pytest.mark.asyncio
    async def test_idempotent_emission(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        test_db_session: AsyncSession,
    ) -> None:
        await emit_completion_metrics(test_db_session, completed_execution, recorder)
        await emit_completion_metrics(test_db_session, completed_execution, recorder)

        assert len(list(recorder.query(metric_types={MetricType.WORKFLOW_DURATION}))) == 1


# ---------------------------------------------------------------------------
# poll_completed_executions (end-to-end with real DB)
# ---------------------------------------------------------------------------


class TestPollCompletedExecutions:
    """End-to-end tests for the ``poll_completed_executions`` callback."""

    def setup_method(self) -> None:
        reset_emission_trackers()

    @pytest.mark.asyncio
    async def test_poll_emits_for_new_execution(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        activities_factory: ActivitiesFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await activities_factory.create_activities(completed_execution, ["step-1"])

        session_factory = async_sessionmaker(test_db_session.bind, class_=AsyncSession, expire_on_commit=False)

        with patch("syntara.metrics.completion_poller.get_metrics_recorder", return_value=recorder):
            await poll_completed_executions(session_factory)

        assert completed_execution.id in emitted_completions
        assert len(list(recorder.query(metric_types={MetricType.WORKFLOW_DURATION}))) == 1
        assert len(list(recorder.query(metric_types={MetricType.ACTIVITY_DURATION}))) == 1

    @pytest.mark.asyncio
    async def test_poll_skips_already_emitted(
        self,
        recorder: MetricsRecorder,
        completed_execution: Execution,
        test_db_session: AsyncSession,
    ) -> None:
        emitted_completions.add(completed_execution.id)

        session_factory = async_sessionmaker(test_db_session.bind, class_=AsyncSession, expire_on_commit=False)

        with patch("syntara.metrics.completion_poller.get_metrics_recorder", return_value=recorder):
            await poll_completed_executions(session_factory)

        assert len(list(recorder.query(metric_types={MetricType.WORKFLOW_DURATION}))) == 0

    @pytest.mark.asyncio
    async def test_poll_ignores_running_execution(
        self,
        recorder: MetricsRecorder,
        executions_factory: ExecutionsFactory,
        test_db_session: AsyncSession,
    ) -> None:
        await executions_factory.create_executions(count=1, status=ExecutionStatus.RUNNING)

        session_factory = async_sessionmaker(test_db_session.bind, class_=AsyncSession, expire_on_commit=False)

        with patch("syntara.metrics.completion_poller.get_metrics_recorder", return_value=recorder):
            await poll_completed_executions(session_factory)

        assert len(list(recorder.query(metric_types={MetricType.WORKFLOW_DURATION}))) == 0


# ---------------------------------------------------------------------------
# Dedup trimming (pure logic, no DB needed)
# ---------------------------------------------------------------------------


class TestDedupTrimming:
    """Tests for dedup set memory management via _BoundedDedup."""

    def setup_method(self) -> None:
        reset_emission_trackers()

    def test_bounded_dedup_evicts_oldest_on_overflow(self) -> None:
        from syntara.metrics.emission import _BoundedDedup

        max_size = 100
        dedup = _BoundedDedup(max_size=max_size)
        ids = [uuid4() for _ in range(max_size + 50)]
        for uid in ids:
            dedup.add(uid)

        assert len(dedup) == max_size
        for uid in ids[:50]:
            assert uid not in dedup
        for uid in ids[50:]:
            assert uid in dedup
