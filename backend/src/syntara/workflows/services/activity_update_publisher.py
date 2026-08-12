"""Activity update publisher for Redis Streams.

This module provides the ActivityUpdatePublisher class for publishing workflow
execution activity updates to Redis Streams for WebSocket streaming to clients.
"""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

import structlog
from jsonpatch import JsonPatch  # type: ignore[import-untyped]

from syntara.core.cache.stream import StreamClient
from syntara.workflows.models.activity_execution import ActivityExecution
from syntara.workflows.models.execution import ActivityData, Execution
from syntara.workflows.models.visualization import (
    ActivityPatchMessage,
    ExecutionPatchMessage,
    ExecutionSnapshotMessage,
    JsonPatchOperation,
)
from syntara.workflows.workflow_engine.utils.credential_scrubber import scrub_credentials

logger = structlog.stdlib.get_logger(__name__)


class ActivityUpdatePublisher:
    """Publishes activity updates to Redis Streams for WebSocket streaming.

    This publisher handles the translation of execution and activity data into
    WebSocket-compatible messages and publishes them to Redis Streams using the
    stream key format: `execution:{execution_id}:events`

    The publisher supports three types of messages:
    - initial_snapshot: Sent on first activity sync with full execution state
    - activity_patch: Sent on incremental updates with JSON Patch operations
    - final_snapshot: Sent when execution reaches terminal state

    Usage:
        publisher = ActivityUpdatePublisher()

        # Publish snapshot
        event_id = await publisher.publish_snapshot(
            execution=execution,
            type="initial_snapshot"
        )

        # Publish patch
        patches = [jsonpatch.make_patch(old_state, new_state)]
        event_id = await publisher.publish_activity_patch(
            execution_id=execution.id,
            activity_updates=patches
        )

    """

    def _get_stream_id(self, execution_id: UUID | str) -> str:
        """Generate stream ID for an execution.

        Args:
            execution_id: The execution UUID or string

        Returns:
            The Redis stream key in format: execution:{execution_id}:events

        """
        return f"execution:{execution_id}:events"

    def _convert_activity_to_data(self, activity: ActivityExecution) -> dict[str, Any]:
        """Convert ActivityExecution to ActivityData format.

        Args:
            activity: The ActivityExecution model instance

        Returns:
            Dict representation in ActivityData format

        """
        return ActivityData(
            activity_id=activity.activity_name,
            status=activity.status,
            started_at=activity.started_at,
            completed_at=activity.completed_at,
            error_details=activity.error_details,
            output_data=activity.output_data,
            iteration=activity.iteration,
        ).model_dump(mode="json")

    def _serialize_execution_snapshot(self, execution: Execution) -> dict[str, Any]:
        """Serialize execution with activities for snapshot messages.

        Args:
            execution: The Execution model instance with loaded activities relationship

        Returns:
            Serialized execution data dictionary with activities in ActivityData format

        """
        # Convert execution to dict (mode="json" serializes UUIDs and datetimes to strings)
        execution_dict = execution.model_dump(mode="json")

        # Convert activities to ActivityData format
        if execution.activities:
            activities_data = [self._convert_activity_to_data(activity) for activity in execution.activities]
            execution_dict["activities"] = activities_data
        else:
            execution_dict["activities"] = []

        return execution_dict

    async def publish_snapshot(
        self,
        execution: Execution,
        snapshot_type: Literal["initial_snapshot", "final_snapshot"],
    ) -> str:
        """Publish execution snapshot to Redis Stream.

        Sends a full snapshot of the execution state including all activities.
        Used for both initial snapshot (first activity sync) and final snapshot
        (execution reaches terminal state).

        Args:
            execution: The Execution model instance with loaded activities relationship
            snapshot_type: The snapshot type - either "initial_snapshot" or "final_snapshot"

        Returns:
            The Redis-generated event ID (e.g., "1642680000000-0")

        Raises:
            RedisConnectionError: If connection to Redis fails
            ValueError: If required parameters are missing or invalid

        """
        stream_id = self._get_stream_id(execution.id)

        # Serialize execution data with activities, scrub credentials
        execution_data = scrub_credentials(self._serialize_execution_snapshot(execution))

        # Create snapshot message
        message = ExecutionSnapshotMessage(
            type=snapshot_type,
            execution_id=str(execution.id),
            event_id="",  # Will be set by Redis
            execution=execution_data,
            timestamp=datetime.now(UTC),
        )

        # Publish to Redis Streams
        async with StreamClient() as client:
            event_id = await client.publish(stream_id, message.model_dump(mode="json", exclude={"event_id"}))
            logger.debug(
                "Published execution snapshot to stream",
                snapshot_type=snapshot_type,
                execution_id=execution.id,
                stream_id=stream_id,
                event_id=event_id,
            )
            return event_id

    async def publish_activity_patch(
        self,
        execution_id: UUID | str,
        activity_updates: list[JsonPatch],
    ) -> str:
        """Publish incremental activity updates as JSON Patch operations.

        Sends a patch message containing JSON Patch operations to apply to the
        activities array. This enables efficient incremental updates.

        Args:
            execution_id: The execution UUID
            activity_updates: List of JsonPatch objects from jsonpatch.make_patch() containing
                            the operations to apply

        Returns:
            The Redis-generated event ID (e.g., "1642680123456-1")

        Raises:
            RedisConnectionError: If connection to Redis fails
            ValueError: If required parameters are missing or invalid

        """
        stream_id = self._get_stream_id(execution_id)

        # Convert list of JsonPatch to list of JsonPatchOperation
        # Scrub credential values from patch operations before publishing
        ops: list[JsonPatchOperation] = []
        for json_patch in activity_updates:
            for patch_op in json_patch.patch:
                # Build operation dict with proper field names
                patch_value = scrub_credentials(patch_op.get("value"))
                op_dict = {
                    "op": patch_op["op"],
                    "path": patch_op["path"],
                    "value": patch_value,
                }
                if "from" in patch_op:
                    op_dict["from"] = patch_op["from"]

                ops.append(JsonPatchOperation(**op_dict))

        # Create activity patch message
        message = ActivityPatchMessage(
            type="activity_patch",
            execution_id=str(execution_id),
            event_id="",  # Will be set by Redis
            ops=ops,
            timestamp=datetime.now(UTC),
        )

        # Publish to Redis Streams
        async with StreamClient() as client:
            event_id = await client.publish(
                stream_id, message.model_dump(mode="json", by_alias=True, exclude={"event_id"})
            )
            logger.debug(
                "Published activity patch to stream",
                execution_id=execution_id,
                stream_id=stream_id,
                event_id=event_id,
                operation_count=len(ops),
            )
            return event_id

    async def publish_execution_patch(
        self,
        execution_id: UUID | str,
        ops: list[JsonPatchOperation],
    ) -> str:
        """Publish execution-level field updates as JSON Patch operations.

        Sends a lightweight patch for execution status changes (e.g. RUNNING→PAUSED)
        instead of resending the full snapshot.

        Args:
            execution_id: The execution UUID
            ops: JSON Patch operations to apply to execution fields

        Returns:
            The Redis-generated event ID

        """
        stream_id = self._get_stream_id(execution_id)

        message = ExecutionPatchMessage(
            type="execution_patch",
            execution_id=str(execution_id),
            event_id="",
            ops=ops,
            timestamp=datetime.now(UTC),
        )

        async with StreamClient() as client:
            event_id = await client.publish(
                stream_id, message.model_dump(mode="json", by_alias=True, exclude={"event_id"})
            )
            logger.debug(
                "Published execution patch to stream",
                execution_id=execution_id,
                stream_id=stream_id,
                event_id=event_id,
                operation_count=len(ops),
            )
            return event_id
