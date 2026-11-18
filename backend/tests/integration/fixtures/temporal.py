"""Temporal workflow engine fixtures for integration tests."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
import structlog
from execution_plane_client.commands.control import CompletionStatus
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from syntara.execution_plane.commands.completion import CompletionCommandHandler
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.workflow_core.models import ActivityName, NodeType
from syntara.workflow_runtime.engines.temporal.activities.condition import condition
from syntara.workflow_runtime.engines.temporal.activities.converge import converge
from syntara.workflow_runtime.engines.temporal.activities.ep.ep_dispatch_activity import (
    execute_bash_script_activity,
    execute_python_script_activity,
)
from syntara.workflow_runtime.engines.temporal.activities.internal_activity import execute_internal_activity
from syntara.workflow_runtime.engines.temporal.activities.manual_trigger import manual_trigger
from syntara.workflow_runtime.engines.temporal.activities.runtime_settings_activity import (
    fetch_workflow_runtime_settings,
)
from syntara.workflow_runtime.engines.temporal.dynamic_workflow import OrchestratorWorkflow
from syntara.workflow_runtime.engines.temporal.services.temporal_execution_service import TemporalExecutionService
from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
from syntara.workflows.models.execution import Execution
from tests.fixtures.fake_execution_plane import FakeExecutionPlaneHttpClient
from tests.fixtures.settings import FakeSettingsCache

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable
    from uuid import UUID

    from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession
    from temporalio.client import Client

logger = structlog.stdlib.get_logger(__name__)

_TEST_WORKER_ACTIVITIES: list[Callable[..., Any]] = [
    execute_python_script_activity,
    execute_bash_script_activity,
    manual_trigger,
    condition,
    converge,
    fetch_workflow_runtime_settings,
    execute_internal_activity,
]


async def _create_temporal_worker(
    temporal_env: WorkflowEnvironment,
) -> AsyncGenerator[Worker, None]:
    """Start a Temporal worker with all registered activities."""
    import syntara.settings.cache.settings_cache as _settings_mod
    from syntara.core.config.base import get_settings

    original = _settings_mod._runtime_settings
    _settings_mod._runtime_settings = FakeSettingsCache()  # type: ignore[assignment]

    settings = get_settings()
    original_script_nodes = settings.script_nodes_enabled
    object.__setattr__(settings, "script_nodes_enabled", True)

    try:
        async with Worker(
            temporal_env.client,
            task_queue="test-workflow-queue",
            workflows=[OrchestratorWorkflow],
            activities=_TEST_WORKER_ACTIVITIES,
        ) as worker:
            yield worker
    finally:
        object.__setattr__(settings, "script_nodes_enabled", original_script_nodes)
        _settings_mod._runtime_settings = original


@pytest_asyncio.fixture(scope="session")
async def _temporal_server() -> AsyncGenerator[WorkflowEnvironment, None]:
    """Provide a Temporal test environment."""
    logger.info("Starting Temporal test environment...")
    async with await WorkflowEnvironment.start_time_skipping() as env:
        logger.info("Temporal test environment started (namespace: %s)", env.client.namespace)
        yield env
    logger.info("Temporal test environment stopped")


@pytest_asyncio.fixture
async def temporal_env(
    _temporal_server: WorkflowEnvironment,
    test_db_engine: AsyncEngine,
    test_db_session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncGenerator[WorkflowEnvironment, None]:
    """Pair Temporal with a test double for the independently deployed EP API."""
    from syntara.execution_plane.utils import execution_plane_work_item_id as original_work_item_id
    from syntara.workflow_runtime.engines.temporal.activities.ep import ep_dispatch_activity

    work_item_activity_ids: dict[UUID, tuple[UUID, str, str, NodeType]] = {}

    def recorded_work_item_id(execution_id: UUID, activity_id: str) -> UUID:
        work_item_id = original_work_item_id(execution_id, activity_id)
        activity_info = activity.info()
        temporal_workflow_id = activity_info.workflow_id
        if temporal_workflow_id is None:
            message = "Cannot correlate fake Execution Plane work without a Temporal workflow ID"
            raise RuntimeError(message)
        node_type = (
            NodeType.SCRIPT_PYTHON
            if str(activity_info.activity_type) == ActivityName.SCRIPT_PYTHON
            else NodeType.SCRIPT_BASH
        )
        work_item_activity_ids[work_item_id] = (execution_id, activity_id, temporal_workflow_id, node_type)
        return work_item_id

    async def deliver_completion(work_item_id: UUID, status: str, result: dict[str, Any]) -> None:
        await asyncio.sleep(0.1)
        execution_id, activity_id, temporal_workflow_id, node_type = work_item_activity_ids[work_item_id]
        async with test_db_session_factory() as session:
            execution = await session.get(Execution, execution_id)
            if execution is None:
                message = f"No execution found for fake Execution Plane work item {work_item_id}"
                raise RuntimeError(message)
            execution.temporal_workflow_id = temporal_workflow_id
            if await session.get(ActivityExecution, work_item_id) is None:
                session.add(
                    ActivityExecution(
                        id=work_item_id,
                        execution_id=execution_id,
                        activity_name=activity_id,
                        node_type=node_type,
                        temporal_activity_id=activity_id,
                        status=ActivityStatus.RUNNING,
                    )
                )
                await session.commit()

        temporal_service = TemporalExecutionService(temporal_client=_temporal_server.client, task_queue="test-queue")
        async with test_db_session_factory() as session:
            delivered = await CompletionCommandHandler()._complete_activity(
                context=AOCommandContext(session, temporal_service),
                work_id=work_item_id,
                status=CompletionStatus(status),
                result=result,
            )
        if not delivered:
            message = f"No activity found for fake Execution Plane work item {work_item_id}"
            raise RuntimeError(message)

    def fake_execution_plane_client(*, timeout: float | None = None) -> FakeExecutionPlaneHttpClient:
        return FakeExecutionPlaneHttpClient(timeout=timeout, on_completion=deliver_completion)

    database_url = test_db_engine.url
    monkeypatch.setenv("APP_DATABASE_URL", database_url.render_as_string(hide_password=False))
    monkeypatch.setattr(ep_dispatch_activity, "execution_plane_work_item_id", recorded_work_item_id)
    monkeypatch.setattr(ep_dispatch_activity, "ExecutionPlaneHttpClient", fake_execution_plane_client)
    monkeypatch.setattr(ep_dispatch_activity, "AsyncSessionLocal", test_db_session_factory)

    with _temporal_server.auto_time_skipping_disabled():
        yield _temporal_server


@pytest_asyncio.fixture
async def temporal_client(temporal_env: WorkflowEnvironment) -> Client:
    """Provide a Temporal client connected to the test environment."""
    return temporal_env.client


@pytest_asyncio.fixture
async def temporal_worker(temporal_env: WorkflowEnvironment) -> AsyncGenerator[Worker, None]:
    """Function-scoped Temporal worker for per-test workflow testing."""
    async for worker in _create_temporal_worker(temporal_env):
        yield worker


@pytest.fixture
def task_queue() -> str:
    """Provide the task queue name for tests."""
    return "test-workflow-queue"
