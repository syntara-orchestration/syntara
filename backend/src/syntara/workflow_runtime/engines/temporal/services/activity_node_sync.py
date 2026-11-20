"""Synchronization of workflow nodes without direct Temporal activity events."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import or_
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from temporalio.client import WorkflowHandle

from syntara.core.constants import FieldLimits
from syntara.workflow_core.models import NodeType
from syntara.workflow_runtime.engines.temporal.services.activity_sync_types import ExecutionMonitorMetadata
from syntara.workflow_runtime.engines.temporal.utils.loop_iteration_ids import (
    loop_iteration_path,
    strip_loop_iteration_suffixes,
)
from syntara.workflows.models.activity_execution import TERMINAL_ACTIVITY_STATUSES, ActivityExecution, ActivityStatus
from syntara.workflows.models.workflow_version import WorkflowVersion

logger = structlog.stdlib.get_logger(__name__)

PRE_RESOLVED_ACTIVITY_ID_PREFIX = "pre-resolved-"
_COMPOSITE_ITER_SEP = "#iter-"


def _input_data_for_activity(
    input_data_map: dict[str, dict[str, Any]] | None,
    activity_name: str,
) -> dict[str, Any] | None:
    """Return mapped inputs for an activity name, falling back to its canvas ID."""
    if not input_data_map:
        return None
    if activity_name in input_data_map:
        return input_data_map[activity_name]
    base_name = activity_name.split(_COMPOSITE_ITER_SEP)[0]
    return input_data_map.get(base_name)


class ActivityNodeSyncMixin:
    """Sync skipped, detached, failed, and pre-resolved workflow nodes."""

    session_factory: Any
    _publish_activity_patches: Any
    _loop_body_activity_ids_by_version: dict[UUID, set[str]]

    async def _fetch_activity_definitions_map(self, workflow_version_id: UUID) -> dict[str, dict[str, Any]]:
        """Fetch activity definitions from V2 workflow version.

        Args:
            workflow_version_id: Workflow version ID

        Returns:
            Dictionary mapping activity/node ID to definition

        """
        async with self.session_factory() as session:
            result = await session.exec(select(WorkflowVersion).where(WorkflowVersion.id == workflow_version_id))
            workflow_version = result.one_or_none()

            activity_definitions_map: dict[str, dict[str, Any]] = {}

            if workflow_version and workflow_version.workflow_definition:
                workflow_def = workflow_version.workflow_definition

                # V2 structure: nodes array at top level
                nodes = workflow_def.get("nodes", [])
                triggers = workflow_def.get("triggers", [])

                # Include triggers as nodes (they create activity records in V2)
                all_nodes = triggers + nodes

                # Build map of all nodes by ID
                for node in all_nodes:
                    if "id" in node:
                        activity_definitions_map[node["id"]] = node

                self._loop_body_activity_ids_by_version[workflow_version_id] = self._extract_loop_body_activity_ids(
                    workflow_def
                )

            return activity_definitions_map

    @staticmethod
    def _extract_loop_body_activity_ids(definition: dict[str, Any]) -> set[str]:
        """Return node IDs reachable from loop iterate edges before feedback."""
        loop_ids = {
            node.get("id")
            for node in [*definition.get("nodes", []), *definition.get("triggers", [])]
            if node.get("type") == NodeType.LOOP and node.get("id")
        }
        edges = definition.get("edges", [])
        body_ids: set[str] = set()

        for loop_id in loop_ids:
            queue = [
                edge["to"]
                for edge in edges
                if edge.get("from") == loop_id and edge.get("from_port") == "iterate" and edge.get("to") != loop_id
            ]
            visited: set[str] = set()
            while queue:
                node_id = queue.pop(0)
                if node_id in visited or node_id == loop_id:
                    continue
                visited.add(node_id)
                is_nested_loop = node_id in loop_ids
                if not is_nested_loop:
                    body_ids.add(node_id)
                next_edges = [edge for edge in edges if edge.get("from") == node_id]
                if is_nested_loop:
                    # A nested loop is a boundary inside the outer body, but its
                    # complete edge continues the outer traversal to the tail.
                    # Following only iterate edges loses that tail activity.
                    next_edges = [edge for edge in next_edges if edge.get("from_port") in ("iterate", "complete")]
                queue.extend(edge["to"] for edge in next_edges if edge.get("to") != loop_id)

        return body_ids

    async def _sync_skipped_nodes(
        self,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
    ) -> None:
        """Query workflow for skipped and pre-resolved nodes and update them in database."""
        skipped_node_ids: list[str] = []
        pre_resolved_node_ids: list[str] = []

        try:
            skipped_node_ids = await handle.query("get_skipped_nodes")
        except Exception:
            logger.exception(
                "Error querying skipped nodes",
                execution_id=metadata.execution_id,
            )

        try:
            pre_resolved_node_ids = await handle.query("get_pre_resolved_nodes")
        except Exception:
            logger.exception(
                "Error querying pre-resolved nodes",
                execution_id=metadata.execution_id,
            )

        all_skipped = list(set(skipped_node_ids) | set(pre_resolved_node_ids))
        if not all_skipped:
            return

        try:
            # Pre-resolved nodes never get Temporal activities, so they may not have
            # ActivityExecution records. Create SKIPPED records for any that are missing.
            if pre_resolved_node_ids:
                await self._ensure_activity_records_exist(metadata, pre_resolved_node_ids, ActivityStatus.SKIPPED)

            await self._sync_nodes_to_terminal_status(
                metadata,
                node_ids=all_skipped,
                target_status=ActivityStatus.SKIPPED,
            )
        except Exception:
            logger.exception(
                "Error syncing skipped nodes to database",
                execution_id=metadata.execution_id,
            )

    async def _sync_detached_nodes(
        self,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
    ) -> None:
        """Query workflow for detached nodes and mark them as CANCELLED in the database.

        Detached nodes were in-flight when a converge ANY strategy fired.  They are
        not in skipped_nodes (the workflow deliberately excludes them so their actual
        Temporal result is preserved when possible), but if the workflow finishes
        before the detached activity completes, the safety net would otherwise label
        them SKIPPED.  Querying here and writing CANCELLED first wins the race against
        _finalize_non_terminal_activities, whose terminal-status guard then leaves the
        record untouched.
        """
        detached_node_ids: list[str] = []
        try:
            detached_node_ids = await handle.query("get_detached_nodes")
        except Exception:
            logger.exception(
                "Error querying detached nodes",
                execution_id=metadata.execution_id,
            )

        if not detached_node_ids:
            return

        try:
            await self._sync_nodes_to_terminal_status(
                metadata,
                node_ids=detached_node_ids,
                target_status=ActivityStatus.CANCELLED,
            )
        except Exception:
            logger.exception(
                "Error syncing detached nodes to cancelled status",
                execution_id=metadata.execution_id,
            )

    async def _ensure_activity_records_exist(
        self,
        metadata: ExecutionMonitorMetadata,
        node_ids: list[str],
        status: ActivityStatus,
    ) -> None:
        """Create ActivityExecution records for nodes that don't have one yet."""
        async with self.session_factory() as session:
            result = await session.exec(
                select(ActivityExecution.activity_name).where(
                    ActivityExecution.execution_id == metadata.execution_id,
                    ActivityExecution.activity_name.in_(node_ids),  # type: ignore[attr-defined]
                )
            )
            existing = set(result.all())
            missing = [nid for nid in node_ids if nid not in existing]

            if not missing:
                return

            now = datetime.now(UTC)
            for node_id in missing:
                activity_def = metadata.activity_definitions_map.get(node_id, {})
                node_type_str = activity_def.get("type", "script")

                # Safely construct NodeType enum with fallback to INTERNAL_ACTIVITY
                try:
                    node_type = NodeType(node_type_str)
                except ValueError:
                    logger.warning(
                        "Invalid node type in workflow definition, defaulting to INTERNAL_ACTIVITY",
                        execution_id=metadata.execution_id,
                        node_id=node_id,
                        invalid_type=node_type_str,
                    )
                    node_type = NodeType.INTERNAL_ACTIVITY

                session.add(
                    ActivityExecution(
                        execution_id=metadata.execution_id,
                        activity_name=node_id,
                        node_type=node_type,
                        temporal_activity_id=f"{PRE_RESOLVED_ACTIVITY_ID_PREFIX}{node_id}"[
                            : FieldLimits.NAME_MAX_LENGTH
                        ],
                        status=status,
                        started_at=now,
                        completed_at=now,
                    )
                )
            await session.commit()
            logger.info(
                "Created activity records for pre-resolved nodes",
                execution_id=metadata.execution_id,
                node_count=len(missing),
            )

    async def _sync_failed_nodes(
        self,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
        *,
        fallback_failed_nodes: dict[str, str] | None = None,
        fallback_input_data: dict[str, dict[str, Any]] | None = None,
        fallback_occurrence_ids: dict[str, str] | None = None,
    ) -> dict[str, str] | None:
        """Query workflow for failed nodes and update them in database.

        Nodes that fail before a Temporal activity is scheduled (e.g., expression
        resolution errors) have no Temporal events, so their ActivityExecution
        records remain PENDING. Nodes that already have a non-PENDING status
        (synced via Temporal events) are left untouched.
        When completion-time queries are rejected, failed nodes and their scrubbed
        inputs are recovered from the workflow completion result.

        Returns:
            Map of node ID to error message for failed nodes, or ``None`` when
            the query fails (distinguishes "no failures" from "query error").

        """
        try:
            failed_node_map: dict[str, str] = await handle.query("get_failed_nodes")
        except Exception:  # noqa: BLE001
            logger.warning(
                "Could not query failed nodes; using workflow completion data",
                execution_id=metadata.execution_id,
                exc_info=True,
            )
            if fallback_failed_nodes:
                try:
                    await self._sync_nodes_to_terminal_status(
                        metadata,
                        node_ids=list(fallback_failed_nodes),
                        target_status=ActivityStatus.FAILED,
                        error_map=fallback_failed_nodes,
                        input_data_map=fallback_input_data,
                        occurrence_id_map=fallback_occurrence_ids,
                    )
                except Exception:
                    logger.exception(
                        "Error syncing failed nodes from workflow completion data",
                        execution_id=metadata.execution_id,
                    )
            return None

        try:
            if fallback_failed_nodes:
                failed_node_map.update(fallback_failed_nodes)
            failed_node_inputs = dict(fallback_input_data or {})
            for node_id in failed_node_map:
                base_node_id = node_id.split(_COMPOSITE_ITER_SEP, maxsplit=1)[0]
                try:
                    input_data = await handle.query("get_activity_input", base_node_id)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "Could not query inputs for failed node",
                        activity_id=node_id,
                        execution_id=metadata.execution_id,
                        exc_info=True,
                    )
                    continue
                if input_data is not None:
                    failed_node_inputs.setdefault(base_node_id, input_data)

            await self._sync_nodes_to_terminal_status(
                metadata,
                node_ids=list(failed_node_map.keys()),
                target_status=ActivityStatus.FAILED,
                error_map=failed_node_map,
                input_data_map=failed_node_inputs,
                occurrence_id_map=fallback_occurrence_ids,
            )
        except Exception:
            logger.exception(
                "Error syncing failed nodes (activities may remain PENDING)",
                execution_id=metadata.execution_id,
            )
            return None
        else:
            return failed_node_map

    def _create_missing_failed_loop_occurrences(
        self,
        session: AsyncSession,
        metadata: ExecutionMonitorMetadata,
        activities: list[ActivityExecution],
        node_ids: list[str],
        error_map: dict[str, str] | None,
        input_data_map: dict[str, dict[str, Any]] | None,
        occurrence_id_map: dict[str, str] | None,
        now: datetime,
    ) -> list[ActivityExecution]:
        """Create failed records for loop occurrences with no scheduled activity event."""
        created: list[ActivityExecution] = []
        if not occurrence_id_map:
            return created

        for base_name, temporal_activity_id in occurrence_id_map.items():
            if (
                base_name not in node_ids
                or strip_loop_iteration_suffixes(temporal_activity_id) != base_name
                or not loop_iteration_path(temporal_activity_id)
            ):
                continue

            base_activities = [
                activity
                for activity in activities
                if activity.activity_name == base_name
                or activity.activity_name.startswith(f"{base_name}{_COMPOSITE_ITER_SEP}")
            ]
            if any(activity.temporal_activity_id == temporal_activity_id for activity in base_activities):
                continue
            if not any(activity.status in TERMINAL_ACTIVITY_STATUSES for activity in base_activities):
                continue

            original = next(
                (activity for activity in base_activities if activity.activity_name == base_name),
                base_activities[0] if base_activities else None,
            )
            if original is None:
                continue
            latest_iteration = max(
                (
                    activity.iteration
                    if activity.iteration is not None
                    else int(activity.activity_name.rpartition(_COMPOSITE_ITER_SEP)[2])
                    if _COMPOSITE_ITER_SEP in activity.activity_name
                    else 0
                    for activity in base_activities
                ),
                default=0,
            )
            iteration = max(latest_iteration, metadata.iteration_counters.get(base_name, 0)) + 1
            composite_key = f"{base_name}{_COMPOSITE_ITER_SEP}{iteration}"
            while any(activity.activity_name == composite_key for activity in base_activities):
                iteration += 1
                composite_key = f"{base_name}{_COMPOSITE_ITER_SEP}{iteration}"

            if original.iteration is None:
                original.iteration = 0
            failed_activity = ActivityExecution(
                execution_id=metadata.execution_id,
                activity_name=composite_key,
                node_type=original.node_type,
                temporal_activity_id=temporal_activity_id,
                status=ActivityStatus.FAILED,
                started_at=None,
                completed_at=now,
                input_data=_input_data_for_activity(input_data_map, base_name) or {},
                output_data=None,
                error_details=(error_map or {}).get(base_name),
                retry_count=0,
                iteration=iteration,
            )
            session.add(failed_activity)
            created.append(failed_activity)
            metadata.iteration_counters[base_name] = iteration
            metadata.activity_index_map[composite_key] = metadata.next_activity_index
            metadata.next_activity_index += 1

        return created

    async def _sync_nodes_to_terminal_status(
        self,
        metadata: ExecutionMonitorMetadata,
        node_ids: list[str],
        target_status: ActivityStatus,
        error_map: dict[str, str] | None = None,
        input_data_map: dict[str, dict[str, Any]] | None = None,
        occurrence_id_map: dict[str, str] | None = None,
    ) -> None:
        """Update ActivityExecution records to a terminal status and publish patches.

        Fetches all activities matching node_ids, then skips any that are already
        in a terminal status. This prevents overwriting one terminal state with
        another (e.g. a COMPLETED activity should not be changed to SKIPPED).
        Already-FAILED rows with empty ``input_data`` still receive a backfill
        from ``input_data_map`` so a completion-payload fallback can fill inputs
        after Temporal already marked the row failed.

        Args:
            metadata: Monitoring metadata containing execution and activity index map
            node_ids: Node IDs to update
            target_status: Terminal status to set (SKIPPED, FAILED, etc.)
            error_map: Optional mapping of node ID to error message
            input_data_map: Optional mapping of failed node IDs to inputs that were
                recorded without a Temporal activity event.
            occurrence_id_map: Optional mapping of failed canvas node IDs to their
                exact Temporal activity IDs, used to persist loop failures that
                occurred before that iteration scheduled an activity.

        """
        if not node_ids:
            return

        execution_id = metadata.execution_id
        logger.debug(
            "Syncing nodes to terminal status",
            execution_id=execution_id,
            target_status=target_status.value,
            node_count=len(node_ids),
        )

        async with self.session_factory() as session:
            # Match base activity names and any per-iteration composite keys (#iter-N)
            name_conditions = [
                ActivityExecution.activity_name.in_(node_ids),  # type: ignore[attr-defined]
                *[ActivityExecution.activity_name.startswith(f"{nid}{_COMPOSITE_ITER_SEP}") for nid in node_ids],
            ]
            result = await session.exec(
                select(ActivityExecution).where(
                    ActivityExecution.execution_id == execution_id,
                    or_(*name_conditions),
                )
            )
            activities = result.all()
            updated_activities: list[tuple[ActivityExecution, dict[str, Any]]] = []
            now = datetime.now(UTC)
            new_iteration_activities = (
                self._create_missing_failed_loop_occurrences(
                    session,
                    metadata,
                    activities,
                    node_ids,
                    error_map,
                    input_data_map,
                    occurrence_id_map,
                    now,
                )
                if target_status == ActivityStatus.FAILED
                else []
            )

            for activity in activities:
                input_data = _input_data_for_activity(input_data_map, activity.activity_name)
                if activity.status in TERMINAL_ACTIVITY_STATUSES:
                    if activity.status == ActivityStatus.FAILED and not activity.input_data and input_data is not None:
                        old_values = {
                            "status": activity.status,
                            "started_at": activity.started_at,
                            "completed_at": activity.completed_at,
                            "error_details": activity.error_details,
                            "output_data": activity.output_data,
                            "iteration": activity.iteration,
                            "input_data": activity.input_data,
                        }
                        activity.input_data = input_data
                        activity.updated_at = now
                        updated_activities.append((activity, old_values))
                    continue
                old_values = {
                    "status": activity.status,
                    "started_at": activity.started_at,
                    "completed_at": activity.completed_at,
                    "error_details": activity.error_details,
                    "output_data": activity.output_data,
                    "iteration": activity.iteration,
                }
                base_name = activity.activity_name.split(_COMPOSITE_ITER_SEP)[0]
                activity.status = target_status
                activity.completed_at = now
                if error_map is not None:
                    activity.error_details = error_map.get(base_name)
                if input_data is not None:
                    activity.input_data = input_data
                activity.updated_at = now
                updated_activities.append((activity, old_values))

            if not updated_activities and not new_iteration_activities:
                return

            await session.commit()

            logger.info(
                "Marked nodes in database",
                execution_id=execution_id,
                target_status=target_status.value,
                count=len(updated_activities),
            )

            await self._publish_activity_patches(
                metadata,
                updated_activities,
                new_iteration_activities=new_iteration_activities,
            )
