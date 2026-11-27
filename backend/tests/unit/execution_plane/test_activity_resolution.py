"""Execution Plane activity resolution strategy behavior."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from syntara.execution_plane.commands.activity_resolution import (
    ActivityResolution,
    ResolutionChain,
    ResolutionStrategy,
    RuntimeContextResolutionStrategy,
    TemporalHistoryResolutionStrategy,
    WorkItemResolutionStrategy,
    resolution_for_activity,
)
from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.utils import execution_plane_work_item_id
from syntara.workflow_core.models import NodeType
from syntara.workflows.models.activity_execution import ActivityExecution
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow_version import WorkflowVersion

if TYPE_CHECKING:
    from collections.abc import Mapping
    from uuid import UUID


class FakeStrategy:
    """Deterministic strategy used to observe chain ordering."""

    def __init__(self, resolution: ActivityResolution | None, *, label: str) -> None:
        """Store the result to return and the calls received."""
        self.resolution = resolution
        self.label = label
        self.calls: list[tuple[AOCommandContext, UUID, Mapping[str, object] | None]] = []

    async def resolve(
        self,
        context: AOCommandContext,
        work_item_id: UUID,
        runtime_context: Mapping[str, object] | None,
    ) -> ActivityResolution | None:
        self.calls.append((context, work_item_id, runtime_context or {}))
        return self.resolution


def resolution() -> ActivityResolution:
    return ActivityResolution(
        execution=SimpleNamespace(),  # type: ignore[arg-type]
        node=SimpleNamespace(),  # type: ignore[arg-type]
        node_type=NodeType.SCRIPT_BASH,
        temporal_activity_id="activity",
    )


@pytest.mark.asyncio
async def test_resolution_chain_stops_at_first_success() -> None:
    expected = resolution()
    context = AOCommandContext(AsyncMock(), None)
    work_item_id = uuid4()
    first = FakeStrategy(None, label="first")
    second = FakeStrategy(expected, label="second")
    third = FakeStrategy(expected, label="third")
    chain = ResolutionChain([first, second, third])

    resolved = await chain.resolve(context, work_item_id, {"execution_id": "execution"})

    assert resolved is expected
    assert len(first.calls) == 1
    assert len(second.calls) == 1
    assert third.calls == []


@pytest.mark.asyncio
async def test_resolution_chain_returns_none_after_all_strategies() -> None:
    context = AOCommandContext(AsyncMock(), None)
    work_item_id = uuid4()
    first = FakeStrategy(None, label="first")
    second = FakeStrategy(None, label="second")
    chain = ResolutionChain([first, second])

    resolved = await chain.resolve(context, work_item_id, None)

    assert resolved is None
    assert len(first.calls) == 1
    assert len(second.calls) == 1


def test_resolution_strategies_are_structurally_interchangeable() -> None:
    assert isinstance(FakeStrategy(None, label="fake"), ResolutionStrategy)


def activity(
    *,
    workflow_definition: dict[str, object] | None = None,
    temporal_activity_id: str = "activity",
) -> ActivityExecution:
    execution = Execution(
        id=uuid4(),
        workflow_id=uuid4(),
        workflow_version_id=uuid4(),
        project_id=uuid4(),
        temporal_workflow_id="workflow",
    )
    definition = workflow_definition or {
        "schema_version": "2.0.0",
        "name": "workflow",
        "triggers": [{"id": "trigger", "type": "manual"}],
        "nodes": [{"id": "approval", "type": "approval", "parameters": {}}],
        "edges": [],
    }
    execution.workflow_version = WorkflowVersion(
        id=execution.workflow_version_id,
        workflow_id=execution.workflow_id,
        version=1,
        schema_version="2.0.0",
        workflow_definition=definition,
    )
    row = ActivityExecution(
        id=uuid4(),
        execution_id=execution.id,
        activity_name="approval",
        node_type="approval",
        temporal_activity_id=temporal_activity_id,
    )
    row.execution = execution
    return row


def execution_result(execution: Execution) -> MagicMock:
    result = MagicMock()
    result.one_or_none.return_value = execution
    return result


def activity_result(row: ActivityExecution | None) -> MagicMock:
    result = MagicMock()
    result.one_or_none.return_value = row
    return result


@pytest.mark.asyncio
async def test_work_item_strategy_resolves_the_persisted_row() -> None:
    row = activity()
    session = AsyncMock()
    session.exec.return_value = activity_result(row)
    context = AOCommandContext(session, None)

    resolution = await WorkItemResolutionStrategy().resolve(context, row.id, None)

    assert resolution is not None
    assert resolution.node is not None
    assert resolution.activity is row
    assert resolution.node.id == "approval"
    session.exec.assert_awaited_once()


@pytest.mark.asyncio
async def test_runtime_context_strategy_resolves_the_exact_iteration_row() -> None:
    execution_id = uuid4()
    temporal_activity_id = "approval_iter_1_iter_0"
    row = activity(temporal_activity_id=temporal_activity_id)
    row.execution_id = execution_id
    row.execution.id = execution_id
    session = AsyncMock()
    session.exec.side_effect = [execution_result(row.execution), activity_result(row)]
    context = AOCommandContext(session, None)
    work_item_id = execution_plane_work_item_id(execution_id, temporal_activity_id)

    resolution = await RuntimeContextResolutionStrategy().resolve(
        context,
        work_item_id,
        {"execution_id": str(execution_id), "temporal_activity_id": temporal_activity_id},
    )

    assert resolution is not None
    assert resolution.activity is row
    assert resolution.temporal_activity_id == temporal_activity_id
    assert session.exec.await_count == 2


@pytest.mark.asyncio
async def test_runtime_context_strategy_rejects_mismatched_work_items() -> None:
    session = AsyncMock()
    context = AOCommandContext(session, None)

    resolution = await RuntimeContextResolutionStrategy().resolve(
        context,
        uuid4(),
        {"execution_id": str(uuid4()), "temporal_activity_id": "approval_iter_0"},
    )

    assert resolution is None
    session.exec.assert_not_awaited()


@pytest.mark.asyncio
async def test_temporal_history_strategy_rejects_terminal_activities() -> None:
    row = activity(
        workflow_definition={
            "schema_version": "2.0.0",
            "name": "workflow",
            "triggers": [{"id": "trigger", "type": "manual"}],
            "nodes": [{"id": "approval", "type": "script_bash", "parameters": {"code": "true"}}],
            "edges": [],
        },
        temporal_activity_id="approval_iter_1",
    )
    execution_id = row.execution.id
    temporal_activity_id = "approval_iter_1"
    work_item_id = execution_plane_work_item_id(execution_id, temporal_activity_id)
    scheduled_event = MagicMock()
    scheduled_event.event_id = 42
    scheduled_event.activity_task_scheduled_event_attributes = SimpleNamespace(
        activity_id=temporal_activity_id,
        activity_type=SimpleNamespace(name="execute_bash_script_activity"),
    )
    completed_event = MagicMock()
    completed_event.activity_task_completed_event_attributes = SimpleNamespace(scheduled_event_id=42)
    history = MagicMock()
    history.events = [scheduled_event, completed_event]
    workflow_handle = AsyncMock()
    workflow_handle.fetch_history.return_value = history
    temporal_client = MagicMock()
    temporal_client.get_workflow_handle.return_value = workflow_handle
    session = AsyncMock()
    session.exec.return_value = execution_result(row.execution)

    resolution = await TemporalHistoryResolutionStrategy().resolve(
        AOCommandContext(session, MagicMock(temporal_client=temporal_client)),
        work_item_id,
        {"execution_id": str(execution_id), "temporal_activity_id": temporal_activity_id},
    )

    assert resolution is None


def test_activity_resolution_matches_canonical_nested_temporal_ids() -> None:
    row = activity()
    row.activity_name = "approval_iter_1_iter_0"
    row.temporal_activity_id = "approval_iter_1_iter_0"

    resolution = resolution_for_activity(row)

    assert resolution is not None
    assert resolution.node is not None
    assert resolution.node.id == "approval"


def test_activity_resolution_prefers_the_longest_ambiguous_canvas_node() -> None:
    definition: dict[str, object] = {
        "schema_version": "2.0.0",
        "name": "workflow",
        "triggers": [{"id": "trigger", "type": "manual"}],
        "nodes": [
            {"id": "approval", "type": "approval", "parameters": {}},
            {"id": "approval_iter_1", "type": "approval", "parameters": {}},
        ],
        "edges": [],
    }
    row = activity(workflow_definition=definition)
    row.activity_name = "approval_iter_1_iter_0"
    row.temporal_activity_id = "approval_iter_1_iter_0"

    resolution = resolution_for_activity(row)

    assert resolution is not None
    assert resolution.node is not None
    assert resolution.node.id == "approval_iter_1"


def test_activity_resolution_rejects_nested_loop_body_collision() -> None:
    definition: dict[str, object] = {
        "schema_version": "2.0.0",
        "name": "workflow",
        "triggers": [{"id": "trigger", "type": "manual"}],
        "nodes": [
            {"id": "outer", "type": "loop", "parameters": {"type": "for_each", "items": "a"}},
            {"id": "inner", "type": "loop", "parameters": {"type": "for_each", "items": "b"}},
            {"id": "approval", "type": "approval", "parameters": {}},
            {"id": "approval_iter_0", "type": "approval", "parameters": {}},
        ],
        "edges": [
            {"from": "outer", "from_port": "iterate", "to": "inner"},
            {"from": "inner", "from_port": "iterate", "to": "approval"},
            {"from": "outer", "from_port": "iterate", "to": "approval_iter_0"},
        ],
    }
    row = activity(workflow_definition=definition)
    row.activity_name = "approval_iter_0_iter_1"
    row.temporal_activity_id = "approval_iter_0_iter_1"

    resolution = resolution_for_activity(row)

    assert resolution is not None
    assert resolution.node is None


def test_activity_resolution_prefers_sole_loop_body_candidate() -> None:
    definition: dict[str, object] = {
        "schema_version": "2.0.0",
        "name": "workflow",
        "triggers": [{"id": "trigger", "type": "manual"}],
        "nodes": [
            {"id": "loop", "type": "loop", "parameters": {"type": "for_each", "items": "a"}},
            {"id": "approval", "type": "approval", "parameters": {}},
            {"id": "approval_iter_0", "type": "approval", "parameters": {}},
        ],
        "edges": [
            {"from": "trigger", "to": "loop"},
            {"from": "loop", "from_port": "iterate", "to": "approval"},
            {"from": "loop", "from_port": "complete", "to": "approval_iter_0"},
        ],
    }
    row = activity(workflow_definition=definition)
    row.activity_name = "approval_iter_0_iter_1"
    row.temporal_activity_id = "approval_iter_0_iter_1"

    resolution = resolution_for_activity(row)

    assert resolution is not None
    assert resolution.node is not None
    assert resolution.node.id == "approval"


def test_activity_resolution_rejects_invalid_workflow_definitions() -> None:
    row = activity(workflow_definition={"schema_version": "invalid"})

    assert resolution_for_activity(row) is None
