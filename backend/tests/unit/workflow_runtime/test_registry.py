"""Contract and import-boundary tests for external activity providers."""

import asyncio
import subprocess
import sys
import threading
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.workflow_runtime.container import ContainerExecutionRequest
from syntara.workflow_runtime.contracts import ActivityContext, ActivityError, Completed, Deferred
from syntara.workflow_runtime.engines.temporal.registered_activities import RegisteredActivities
from syntara.workflow_runtime.registry import ActivityDefinition, ActivityRegistry
from tests.fixtures.temporal import CompleteAsyncError


def test_business_provider_imports_without_temporal() -> None:
    """Block SDK imports in a fresh interpreter, including transitive imports."""
    result = subprocess.run(  # noqa: S603 -- fixed interpreter and literal test program
        [
            sys.executable,
            "-c",
            """
import importlib.abc
import sys
class BlockTemporal(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'temporalio' or fullname.startswith('temporalio.'):
            raise AssertionError(fullname)
sys.meta_path.insert(0, BlockTemporal())
import syntara.workflow_runtime.contracts
import syntara.workflow_runtime.registry
import syntara.workflow_runtime.completion
import syntara.approvals.registration
import syntara.invocations.registration
""",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_duplicate_and_missing_versions_fail() -> None:
    """A deployment cannot silently replace a pinned implementation."""
    registry = ActivityRegistry()
    definition = ActivityDefinition("example", 1, lambda _inputs, _context: Completed({}))
    registry.register(definition)
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(definition)
    with pytest.raises(ActivityError, match="not installed"):
        registry.resolve("example", 2)


@pytest.mark.asyncio
async def test_sync_handler_runs_off_event_loop() -> None:
    """Blocking handlers must not block the worker's async event loop."""
    event_loop_thread = threading.get_ident()
    definition = ActivityDefinition("thread", 1, lambda _inputs, _context: Completed({"thread": threading.get_ident()}))
    context = ActivityContext(uuid4(), uuid4(), "node", "key")
    outcome = await definition.invoke({}, context)
    assert isinstance(outcome, Completed)
    assert outcome.output["thread"] != event_loop_thread


@pytest.mark.asyncio
async def test_async_handler_returns_completed() -> None:
    """Python async execution does not imply deferred activity completion."""
    handler = AsyncMock(return_value=Completed({"value": 3}))
    definition = ActivityDefinition("async", 1, handler)
    context = ActivityContext(uuid4(), uuid4(), "node", "key")
    assert await definition.invoke({}, context) == Completed({"value": 3})


@pytest.mark.asyncio
async def test_foreign_or_undeclared_deferral_is_rejected() -> None:
    """A handler cannot complete another activity or opt into deferral at runtime."""
    context = ActivityContext(uuid4(), uuid4(), "node", "key", uuid4())
    handler = AsyncMock(return_value=Deferred(uuid4(), "external"))
    for supports_deferred in (False, True):
        definition = ActivityDefinition("deferred", 1, handler, supports_deferred=supports_deferred)
        with pytest.raises(ActivityError, match="unauthorized"):
            await definition.invoke({}, context)


@pytest.mark.asyncio
async def test_adapter_defers_only_after_persisted_handoff() -> None:
    """The domain return becomes an SDK deferral, never a normal activity result."""
    registry = ActivityRegistry()
    reference = uuid4()
    registry.register(
        ActivityDefinition(
            "approval.request", 1, AsyncMock(return_value=Deferred(reference, "approval")), supports_deferred=True
        )
    )
    adapter = RegisteredActivities(registry, MagicMock(), MagicMock())
    handoff = AsyncMock()
    with (
        patch.object(adapter, "_reserve", AsyncMock(return_value=reference)),
        patch.object(adapter, "_handoff", handoff),
        patch("temporalio.activity.info", return_value=MagicMock(activity_id="approval_iter_2")),
        patch("temporalio.activity.heartbeat"),
    ):
        with pytest.raises(CompleteAsyncError):
            await adapter.execute(
                {
                    "name": "approval.request",
                    "version": 1,
                    "input": {},
                    "execution_id": str(uuid4()),
                    "project_id": str(uuid4()),
                }
            )
    handoff.assert_awaited_once_with(reference, Deferred(reference, "approval"))


@pytest.mark.asyncio
async def test_adapter_routes_container_activity_to_executor() -> None:
    """Container metadata selects the injected execution boundary."""
    registry = ActivityRegistry()
    definition = ActivityDefinition(
        "http_request.execute",
        1,
        AsyncMock(side_effect=AssertionError("worker handler must not run")),
        execution_mode="container",
        container_image="example/http-runner:dev",
    )
    registry.register(definition)
    executor = MagicMock()
    executor.run = AsyncMock(return_value=Completed({"status_code": 200}))
    adapter = RegisteredActivities(registry, MagicMock(), MagicMock(), container_executor=executor)
    execution_id = uuid4()
    project_id = uuid4()

    with patch("temporalio.activity.info", return_value=MagicMock(activity_id="http_1")):
        result = await adapter.execute(
            {
                "name": "http_request.execute",
                "version": 1,
                "input": {"url": "https://example.com"},
                "execution_id": str(execution_id),
                "project_id": str(project_id),
            }
        )

    assert result == {"output": {"status_code": 200}}
    executor.run.assert_awaited_once()
    request, context = executor.run.await_args.args
    assert isinstance(request, ContainerExecutionRequest)
    assert request.image == "example/http-runner:dev"
    assert request.input == {"url": "https://example.com"}
    assert context.execution_id == execution_id


@pytest.mark.asyncio
async def test_adapter_invokes_registered_lifecycle_hook() -> None:
    """Lifecycle operations use the provider hook attached to the activity."""
    registry = ActivityRegistry()
    cancel = AsyncMock(return_value=Completed({"cancelled_count": 1}))
    registry.register(
        ActivityDefinition(
            "approval.request",
            1,
            AsyncMock(),
            supports_deferred=True,
            cancel_handler=cancel,
        )
    )
    adapter = RegisteredActivities(registry, MagicMock(), MagicMock())
    execution_id = uuid4()
    project_id = uuid4()

    with patch("temporalio.activity.info", return_value=MagicMock(activity_id="cancel_1")):
        result = await adapter.execute(
            {
                "name": "approval.request",
                "version": 1,
                "operation": "cancel",
                "input": {"reason": "workflow cancelled"},
                "execution_id": str(execution_id),
                "project_id": str(project_id),
            }
        )

    assert result == {"output": {"cancelled_count": 1}}
    cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_handler_cancellation_propagates() -> None:
    """Cancellation is not translated into a successful output or ordinary failure."""
    definition = ActivityDefinition("cancelled", 1, AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        await definition.invoke({}, ActivityContext(uuid4(), uuid4(), "node", "key"))
