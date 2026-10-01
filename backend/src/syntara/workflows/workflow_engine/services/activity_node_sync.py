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
from syntara.workflows.workflow_engine.models.workflow_definition import NodeType
from syntara.workflows.workflow_engine.services.activity_sync_types import ExecutionMonitorMetadata
from syntara.workflows.workflow_engine.services.retry_activity_sync import sync_restored_activities

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
        await self._sync_restored_retry_nodes(metadata, handle)
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

    async def _sync_restored_retry_nodes(
        self,
        metadata: ExecutionMonitorMetadata,
        handle: WorkflowHandle[Any, Any],
    ) -> None:
        """Persist supplied retry completions, which emit no node activity events."""
        if not metadata.is_retry:
            return
        try:
            restored = await handle.query("get_restored_nodes")
            if not restored:
                return
            async with self.session_factory() as session:
                updated, created = await sync_restored_activities(session, metadata.execution_id, restored)
                await session.commit()
            for row in [item[0] for item in updated] + created:
                name = row.activity_name
                if _COMPOSITE_ITER_SEP in name:
                    base_id, _, suffix = name.rpartition(_COMPOSITE_ITER_SEP)
                    metadata.iteration_counters[base_id] = max(metadata.iteration_counters.get(base_id, 0), int(suffix))
                else:
                    metadata.terminal_activity_ids.add(name)
                if name not in metadata.activity_index_map:
                    metadata.activity_index_map[name] = metadata.next_activity_index
                    metadata.next_activity_index += 1
            await self._publish_activity_patches(metadata, updated, new_iteration_activities=created)
        except Exception:
            logger.exception("Error syncing restored retry nodes", execution_id=metadata.execution_id)

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
