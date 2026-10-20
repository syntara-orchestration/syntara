"""Synchronization of workflow nodes without direct Temporal activity events."""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import or_
from sqlmodel import select
from temporalio.client import WorkflowHandle

from syntara.core.constants import FieldLimits
from syntara.workflows.models.activity_execution import TERMINAL_ACTIVITY_STATUSES, ActivityExecution, ActivityStatus
from syntara.workflows.models.workflow_version import WorkflowVersion
from syntara.workflows.utils.datetime import ensure_timezone_aware
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.services.activity_sync_types import ExecutionMonitorMetadata
from syntara.workflows.workflow_engine.utils.loop_iteration_ids import loop_iteration_path

logger = structlog.stdlib.get_logger(__name__)

PRE_RESOLVED_ACTIVITY_ID_PREFIX = "pre-resolved-"
_COMPOSITE_ITER_SEP = "#iter-"


class ActivityNodeSyncMixin:
    """Sync skipped, detached, failed, and pre-resolved workflow nodes."""

    session_factory: Any
    _publish_activity_patches: Any

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

            return activity_definitions_map

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
    ) -> dict[str, str] | None:
        """Query workflow for failed nodes and update them in database.

        Nodes that fail before a Temporal activity is scheduled (e.g., expression
        resolution errors) have no Temporal events, so their ActivityExecution
        records remain PENDING. Nodes that already have a non-PENDING status
        (synced via Temporal events) are left untouched.

        Returns:
            Map of node ID to error message for failed nodes, or ``None`` when
            the query fails (distinguishes "no failures" from "query error").

        """
        try:
            failed_node_map: dict[str, str] = await handle.query("get_failed_nodes")
            await self._sync_nodes_to_terminal_status(
                metadata,
                node_ids=list(failed_node_map.keys()),
                target_status=ActivityStatus.FAILED,
                error_map=failed_node_map,
                handle=handle,
            )
        except Exception:
            logger.exception(
                "Error syncing failed nodes (activities may remain PENDING)",
                execution_id=metadata.execution_id,
            )
            return None
        else:
            return failed_node_map

    async def _sync_nodes_to_terminal_status(
        self,
        metadata: ExecutionMonitorMetadata,
        node_ids: list[str],
        target_status: ActivityStatus,
        error_map: dict[str, str] | None = None,
        handle: WorkflowHandle[Any, Any] | None = None,
    ) -> None:
        """Update ActivityExecution records to a terminal status and publish patches.

        Fetches all activities matching node_ids, then skips any that are already
        in a terminal status. This prevents overwriting one terminal state with
        another (e.g. a COMPLETED activity should not be changed to SKIPPED).

        Args:
            metadata: Monitoring metadata containing execution and activity index map
            node_ids: Node IDs to update
            target_status: Terminal status to set (SKIPPED, FAILED, etc.)
            error_map: Optional mapping of node ID to error message
            handle: Temporal handle used to check loop converge replay eligibility

        """
        if not node_ids:
            return

        execution_id = metadata.execution_id
        source_converge_timestamps = (
            await self._retry_converge_source_timestamps(metadata, node_ids, handle)
            if target_status == ActivityStatus.FAILED
            else {}
        )
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

            if not activities:
                return

            updated_activities: list[tuple[ActivityExecution, dict[str, Any]]] = []
            now = datetime.now(UTC)
            for activity in activities:
                if activity.status in TERMINAL_ACTIVITY_STATUSES:
                    continue
                old_values = {
                    "status": activity.status,
                    "started_at": activity.started_at,
                    "completed_at": activity.completed_at,
                    "error_details": activity.error_details,
                    "output_data": activity.output_data,
                    "iteration": activity.iteration,
                }
                activity.status = target_status
                activity.completed_at = now
                source_timestamps = source_converge_timestamps.get(activity.temporal_activity_id)
                if source_timestamps is not None:
                    activity.started_at, activity.completed_at = source_timestamps
                if error_map is not None:
                    base_name = activity.activity_name.split(_COMPOSITE_ITER_SEP)[0]
                    activity.error_details = error_map.get(base_name)
                activity.updated_at = now
                updated_activities.append((activity, old_values))

            if not updated_activities:
                return

            await session.commit()

            logger.info(
                "Marked nodes in database",
                execution_id=execution_id,
                target_status=target_status.value,
                count=len(updated_activities),
            )

            await self._publish_activity_patches(metadata, updated_activities)

    async def _retry_converge_source_timestamps(
        self,
        metadata: ExecutionMonitorMetadata,
        node_ids: list[str],
        handle: WorkflowHandle[Any, Any] | None,
    ) -> dict[str, tuple[datetime | None, datetime | None]]:
        """Load source times for eligible converge occurrences failed during retry.

        Loop occurrences are eligible only when the workflow confirms every direct
        branch input was replayed. Temporal queries happen between short database
        reads, never while a session is open.
        """
        if not metadata.is_retry_from_failure or metadata.retry_source_execution_id is None:
            return {}

        if not self._retry_has_converge_nodes(metadata, node_ids):
            return {}

        name_conditions = [
            ActivityExecution.activity_name.in_(node_ids),  # type: ignore[attr-defined]
            *[ActivityExecution.activity_name.startswith(f"{node_id}{_COMPOSITE_ITER_SEP}") for node_id in node_ids],
        ]
        async with self.session_factory() as session:
            current_result = await session.exec(
                select(
                    ActivityExecution.activity_name,
                    ActivityExecution.temporal_activity_id,
                    ActivityExecution.status,
                ).where(
                    ActivityExecution.execution_id == metadata.execution_id,
                    or_(*name_conditions),
                )
            )
            current_activities = current_result.all()

        source_temporal_ids = await self._eligible_retry_converge_source_ids(metadata, current_activities, handle)
        if not source_temporal_ids:
            return {}

        async with self.session_factory() as session:
            source_result = await session.exec(
                select(
                    ActivityExecution.temporal_activity_id,
                    ActivityExecution.status,
                    ActivityExecution.started_at,
                    ActivityExecution.completed_at,
                ).where(
                    ActivityExecution.execution_id == metadata.retry_source_execution_id,
                    ActivityExecution.temporal_activity_id.in_(source_temporal_ids),  # type: ignore[attr-defined]
                )
            )
        source_timestamps: dict[str, tuple[datetime | None, datetime | None]] = {}
        for temporal_activity_id, source_status, started_at, completed_at in source_result.all():
            if source_status in (ActivityStatus.COMPLETED, ActivityStatus.FAILED):
                source_timestamps[temporal_activity_id] = (
                    ensure_timezone_aware(started_at) if started_at else None,
                    ensure_timezone_aware(completed_at) if completed_at else None,
                )
        return source_timestamps

    @staticmethod
    def _retry_has_converge_nodes(metadata: ExecutionMonitorMetadata, node_ids: list[str]) -> bool:
        """Whether a failed-node sync needs the extra converge timestamp lookup."""
        return any(
            metadata.activity_definitions_map.get(node_id.split(_COMPOSITE_ITER_SEP, maxsplit=1)[0], {}).get("type")
            == NodeType.CONVERGE
            for node_id in node_ids
        )

    async def _eligible_retry_converge_source_ids(
        self,
        metadata: ExecutionMonitorMetadata,
        current_activities: list[tuple[str, str, ActivityStatus]],
        handle: WorkflowHandle[Any, Any] | None,
    ) -> set[str]:
        """Collect current converge occurrences whose source times are safe to reuse."""
        source_temporal_ids: set[str] = set()
        for activity_name, temporal_activity_id, status in current_activities:
            if status in TERMINAL_ACTIVITY_STATUSES or not temporal_activity_id:
                continue
            base_name = activity_name.split(_COMPOSITE_ITER_SEP, maxsplit=1)[0]
            if metadata.activity_definitions_map.get(base_name, {}).get("type") != NodeType.CONVERGE:
                continue

            if loop_iteration_path(temporal_activity_id) and not await self._should_preserve_loop_converge_timestamps(
                temporal_activity_id, metadata, handle
            ):
                continue
            source_temporal_ids.add(temporal_activity_id)
        return source_temporal_ids

    async def _should_preserve_loop_converge_timestamps(
        self,
        temporal_activity_id: str,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any] | None,
    ) -> bool:
        """Ask the active workflow whether this loop converge's inputs all replayed."""
        if handle is None:
            return False
        try:
            return bool(await handle.query("should_preserve_loop_converge_timestamps", temporal_activity_id))
        except Exception:
            logger.exception(
                "Could not determine whether loop converge branches were replayed",
                activity_id=temporal_activity_id,
                execution_id=metadata.execution_id,
            )
            return False
