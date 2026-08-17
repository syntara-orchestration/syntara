"""Temporal workflow engine fixtures for integration tests."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
import pytest_asyncio
import structlog
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from syntara.workflows.workflow_engine.activities.condition import condition
from syntara.workflows.workflow_engine.activities.converge import converge
from syntara.workflows.workflow_engine.activities.internal_activity import execute_internal_activity
from syntara.workflows.workflow_engine.activities.manual_trigger import manual_trigger
from syntara.workflows.workflow_engine.activities.runtime_settings_activity import fetch_workflow_runtime_settings
from syntara.workflows.workflow_engine.activities.script_activity import execute_script_activity
from syntara.workflows.workflow_engine.dynamic_workflow import OrchestratorWorkflow

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Callable

    from temporalio.client import Client

logger = structlog.stdlib.get_logger(__name__)

_TEST_WORKER_ACTIVITIES: list[Callable[..., Any]] = [
    execute_script_activity,
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
    from tests.fixtures.settings import FakeSettingsCache

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
async def temporal_env() -> AsyncGenerator[WorkflowEnvironment, None]:
    """Provide a Temporal test environment."""
    logger.info("Starting Temporal test environment...")
    async with await WorkflowEnvironment.start_time_skipping() as env:
        logger.info("Temporal test environment started (namespace: %s)", env.client.namespace)
        yield env
    logger.info("Temporal test environment stopped")


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
