"""Resolution strategies for Execution Plane command activities."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.orm import selectinload
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.execution_plane.commands.context import AOCommandContext
from syntara.execution_plane.utils import (
    execution_plane_supported_node_types,
    runtime_context_activity_identity,
)
from syntara.workflow_core.models import ActivityName, NodeType
from syntara.workflow_runtime.engines.temporal.services.temporal_execution_service import (
    TemporalExecutionService,
)
from syntara.workflow_runtime.engines.temporal.utils.loop_iteration_ids import (
    extract_loop_body_node_ids,
    resolve_loop_iteration_canvas_id,
)
from syntara.workflows.models.activity_execution import TERMINAL_ACTIVITY_STATUSES, ActivityExecution
from syntara.workflows.models.execution import Execution
from syntara.workflows.models.workflow_definition import WorkflowDefinition, WorkflowNode

if TYPE_CHECKING:
    from syntara.workflows.models.workflow_version import WorkflowVersion


@dataclass(frozen=True)
class _TemporalActivityReference:
    """A Temporal-scheduled activity and its canvas workflow node."""

    execution: Execution
    temporal_activity_id: str
    node: WorkflowNode


@dataclass(frozen=True)
class ActivityResolution:
    """A canvas activity resolved for an Execution Plane callback."""

    execution: Execution
    node: WorkflowNode | None
    node_type: NodeType
    temporal_activity_id: str
    activity: ActivityExecution | None = None


@runtime_checkable
class ResolutionStrategy(Protocol):
    """Resolve an activity from one authoritative source."""

    async def resolve(
        self,
        context: AOCommandContext,
        work_item_id: UUID,
        runtime_context: Mapping[str, object] | None,
    ) -> ActivityResolution | None:
        """Return the resolved activity, or None so the next strategy can run."""
        ...


class ResolutionChain:
    """Try resolution strategies in order and stop at the first success."""

    def __init__(self, strategies: Sequence[ResolutionStrategy]) -> None:
        """Store the strategies in their resolution order."""
        self._strategies = tuple(strategies)

    async def resolve(
        self,
        context: AOCommandContext,
        work_item_id: UUID,
        runtime_context: Mapping[str, object] | None,
    ) -> ActivityResolution | None:
        """Resolve through the first strategy that can identify the activity."""
        for strategy in self._strategies:
            resolution = await strategy.resolve(context, work_item_id, runtime_context)
            if resolution is not None:
                return resolution
        return None


class WorkItemResolutionStrategy:
    """Resolve a callback from the persisted activity whose ID is the work item."""

    async def resolve(
        self,
        context: AOCommandContext,
        work_item_id: UUID,
        runtime_context: Mapping[str, object] | None,
    ) -> ActivityResolution | None:
        """Resolve by activity ID from the persisted activity row."""
        del runtime_context
        result = await context.session.exec(
            select(ActivityExecution)
            .where(col(ActivityExecution.id) == work_item_id)
            .options(
                selectinload(ActivityExecution.execution).selectinload(Execution.workflow_version),  # type: ignore[arg-type]
            )
        )
        activity = result.one_or_none()
        return resolution_for_activity(activity) if activity is not None else None


class RuntimeContextResolutionStrategy:
    """Resolve loop-body callbacks from correlated persisted activity rows."""

    async def resolve(
        self,
        context: AOCommandContext,
        work_item_id: UUID,
        runtime_context: Mapping[str, object] | None,
    ) -> ActivityResolution | None:
        """Resolve by correlated execution and Temporal activity IDs."""
        identity = runtime_context_activity_identity(work_item_id, runtime_context)
        if identity is None:
            return None
        execution_uuid, temporal_activity_id = identity

        execution_result = await context.session.exec(
            select(Execution)
            .where(col(Execution.id) == execution_uuid)
            .options(selectinload(Execution.workflow_version))  # type: ignore[arg-type]
        )
        execution = execution_result.one_or_none()
        if execution is None or execution.workflow_version is None:
            return None
        try:
            definition = WorkflowDefinition.model_validate(execution.workflow_version.workflow_definition)
        except ValidationError:
            return None
        base_activity_id = resolve_loop_iteration_canvas_id(
            temporal_activity_id,
            (node.id for node in definition.nodes),
            extract_loop_body_node_ids(execution.workflow_version.workflow_definition),
        )
        if base_activity_id is None:
            return None

        result = await context.session.exec(
            select(ActivityExecution)
            .where(
                col(ActivityExecution.execution_id) == execution_uuid,
                col(ActivityExecution.temporal_activity_id) == temporal_activity_id,
            )
            .options(
                selectinload(ActivityExecution.execution).selectinload(Execution.workflow_version),  # type: ignore[arg-type]
            )
        )
        activity = result.one_or_none()
        if activity is None:
            result = await context.session.exec(
                select(ActivityExecution)
                .where(
                    col(ActivityExecution.execution_id) == execution_uuid,
                    col(ActivityExecution.activity_name) == base_activity_id,
                    col(ActivityExecution.temporal_activity_id) == base_activity_id,
                )
                .options(
                    selectinload(ActivityExecution.execution).selectinload(Execution.workflow_version),  # type: ignore[arg-type]
                )
            )
            activity = result.one_or_none()
            if activity is not None and activity.status in TERMINAL_ACTIVITY_STATUSES:
                return None
        return (
            resolution_for_activity(activity, temporal_activity_id=temporal_activity_id)
            if activity is not None
            else None
        )


class TemporalHistoryResolutionStrategy:
    """Resolve a callback from Temporal history before its database row exists."""

    async def resolve(
        self,
        context: AOCommandContext,
        work_item_id: UUID,
        runtime_context: Mapping[str, object] | None,
    ) -> ActivityResolution | None:
        """Resolve from the scheduled activity in Temporal history."""
        reference = await _load_temporal_activity(context, work_item_id, runtime_context)
        if reference is None:
            return None
        return ActivityResolution(
            execution=reference.execution,
            node=reference.node,
            node_type=NodeType(reference.node.type),
            temporal_activity_id=reference.temporal_activity_id,
        )


async def _load_temporal_activity(
    context: AOCommandContext,
    work_item_id: UUID,
    runtime_context: Mapping[str, object] | None,
) -> _TemporalActivityReference | None:
    """Resolve a work item from Temporal history before its database row exists."""
    identity = runtime_context_activity_identity(work_item_id, runtime_context)
    temporal_service = context.temporal_service
    if identity is None or temporal_service is None:
        return None
    execution_uuid, temporal_activity_id = identity

    execution = await _load_execution(context.session, execution_uuid)
    node = _canvas_node_for_activity(execution, temporal_activity_id) if execution is not None else None
    if execution is None or node is None:
        return None
    return await _activity_from_history(temporal_service, execution, temporal_activity_id, node)


async def _load_execution(session: AsyncSession, execution_uuid: UUID) -> Execution | None:
    execution_result = await session.exec(
        select(Execution).where(col(Execution.id) == execution_uuid).options(selectinload(Execution.workflow_version))  # type: ignore[arg-type]
    )
    return execution_result.one_or_none()


def _canvas_node_for_activity(execution: Execution, temporal_activity_id: str) -> WorkflowNode | None:
    workflow_version: WorkflowVersion | None = execution.workflow_version
    if workflow_version is None:
        return None
    try:
        definition = WorkflowDefinition.model_validate(workflow_version.workflow_definition)
    except ValidationError:
        return None

    canvas_activity_id = resolve_loop_iteration_canvas_id(
        temporal_activity_id,
        (node.id for node in definition.nodes),
        extract_loop_body_node_ids(workflow_version.workflow_definition),
    )
    if canvas_activity_id is None:
        return None
    return next((candidate for candidate in definition.nodes if candidate.id == canvas_activity_id), None)


async def _activity_from_history(
    temporal_service: TemporalExecutionService,
    execution: Execution,
    temporal_activity_id: str,
    node: WorkflowNode,
) -> _TemporalActivityReference | None:
    node_type = NodeType(node.type)
    if node_type not in execution_plane_supported_node_types():
        return None
    expected_activity_name = ActivityName[node_type.name]
    workflow_handle = temporal_service.temporal_client.get_workflow_handle(execution.temporal_workflow_id)
    history = await workflow_handle.fetch_history()
    scheduled_event = None
    for event in history.events:
        attrs = event.activity_task_scheduled_event_attributes
        if (
            attrs is not None
            and attrs.activity_id == temporal_activity_id
            and attrs.activity_type is not None
            and attrs.activity_type.name == expected_activity_name.value
        ):
            scheduled_event = event
            break
    if scheduled_event is None:
        return None

    terminal = False
    for event in history.events:
        started = event.activity_task_started_event_attributes
        if started is not None and started.scheduled_event_id == scheduled_event.event_id:
            terminal = False

        terminal_attributes = (
            event.activity_task_completed_event_attributes,
            event.activity_task_failed_event_attributes,
            event.activity_task_timed_out_event_attributes,
            event.activity_task_canceled_event_attributes,
        )
        if any(
            attrs is not None and attrs.scheduled_event_id == scheduled_event.event_id for attrs in terminal_attributes
        ):
            terminal = True

    if terminal:
        return None
    return _TemporalActivityReference(
        execution=execution,
        temporal_activity_id=temporal_activity_id,
        node=node,
    )


def resolution_for_activity(
    activity: ActivityExecution,
    *,
    temporal_activity_id: str | None = None,
) -> ActivityResolution | None:
    """Resolve a persisted activity row to its canvas node and execution."""
    execution = activity.execution
    workflow_version = execution.workflow_version
    try:
        definition = WorkflowDefinition.model_validate(workflow_version.workflow_definition)
    except ValidationError:
        return None

    node_ids = tuple(node.id for node in definition.nodes)
    loop_body_node_ids = extract_loop_body_node_ids(workflow_version.workflow_definition)
    canvas_activity_id = resolve_loop_iteration_canvas_id(
        temporal_activity_id or activity.temporal_activity_id,
        node_ids,
        loop_body_node_ids,
    )
    if canvas_activity_id is None:
        canvas_activity_id = resolve_loop_iteration_canvas_id(activity.activity_name, node_ids, loop_body_node_ids)
    node = None
    if canvas_activity_id is not None:
        node = next((candidate for candidate in definition.nodes if candidate.id == canvas_activity_id), None)
    if node is None:
        legacy_matches = [
            candidate for candidate in definition.nodes if activity.activity_name.startswith(f"{candidate.id}#iter-")
        ]
        node = max(legacy_matches, key=lambda candidate: len(candidate.id)) if legacy_matches else None
    return ActivityResolution(
        execution=execution,
        node=node,
        node_type=activity.node_type,
        temporal_activity_id=temporal_activity_id or activity.temporal_activity_id,
        activity=activity,
    )
