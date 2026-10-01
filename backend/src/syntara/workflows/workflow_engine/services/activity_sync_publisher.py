"""Incremental JSON Patch publishing for activity execution updates."""

from typing import Any

import structlog
from jsonpatch import JsonPatch  # type: ignore[import-untyped]

from syntara.workflows.models.activity_execution import ActivityExecution
from syntara.workflows.models.execution import ActivityData
from syntara.workflows.workflow_engine.services.activity_sync_types import ExecutionMonitorMetadata

logger = structlog.stdlib.get_logger(__name__)
_COMPOSITE_ITER_SEP = "#iter-"


class ActivitySyncPublisherMixin:
    """Build and publish activity-level JSON Patch operations."""

    activity_publisher: Any

    @staticmethod
    def _build_field_patch_ops(
        activity: ActivityExecution,
        old_values: dict[str, Any],
        activity_idx: int,
    ) -> list[dict[str, Any]]:
        """Build JSON Patch "replace" ops for changed fields on a single activity."""
        ops: list[dict[str, Any]] = []
        fields_to_check = [
            ("status", activity.status.value if activity.status else None),
            ("started_at", activity.started_at.isoformat() if activity.started_at else None),
            ("completed_at", activity.completed_at.isoformat() if activity.completed_at else None),
            ("error_details", activity.error_details),
            ("output_data", activity.output_data),
            ("iteration", activity.iteration),
        ]

        for field_name, new_value in fields_to_check:
            old_value = old_values.get(field_name)
            if field_name == "status" and old_value is not None:
                old_value = old_value.value
            elif field_name in ("started_at", "completed_at") and old_value is not None:
                old_value = old_value.isoformat()
            if old_value != new_value:
                ops.append({"op": "replace", "path": f"/activities/{activity_idx}/{field_name}", "value": new_value})

        return ops

    @staticmethod
    def _build_iteration_patch_ops(
        new_iteration_activities: list[ActivityExecution],
        activity_index_map: dict[str, int],
    ) -> list[dict[str, Any]]:
        """Build JSON Patch ops for newly created per-iteration activity records.

        Generates "add" ops to append new records to the activities array, plus
        "replace" ops to set ``iteration=0`` on original records.

        """
        ops: list[dict[str, Any]] = []
        patched_originals: set[str] = set()

        for activity in new_iteration_activities:
            data = ActivityData(
                activity_id=activity.activity_name,
                status=activity.status.value if activity.status else "pending",
                started_at=activity.started_at,
                completed_at=activity.completed_at,
                error_details=activity.error_details,
                output_data=activity.output_data,
                iteration=activity.iteration,
            )
            ops.append({"op": "add", "path": "/activities/-", "value": data.model_dump(mode="json")})

            base_id = activity.activity_name.split(_COMPOSITE_ITER_SEP)[0]
            if base_id not in patched_originals:
                original_idx = activity_index_map.get(base_id)
                if original_idx is not None:
                    ops.append({"op": "replace", "path": f"/activities/{original_idx}/iteration", "value": 0})
                    patched_originals.add(base_id)

        return ops

    async def _publish_activity_patches(
        self,
        metadata: ExecutionMonitorMetadata,
        updated_activities: list[tuple[ActivityExecution, dict[str, Any]]],
        *,
        new_iteration_activities: list[ActivityExecution] | None = None,
    ) -> None:
        """Publish activity patches for incremental updates.

        Creates JSON Patch operations manually without costly DB reads by directly
        constructing patch operations for each changed field. For newly created
        per-iteration records, publishes "add" ops to append to the activities array.

        Args:
            metadata: Monitoring metadata containing execution and activity index map
            updated_activities: List of (activity, old_values) tuples for activities that were updated
            new_iteration_activities: Newly created per-iteration records needing "add" ops

        """
        execution_id = metadata.execution_id
        new_activity_names = {a.activity_name for a in (new_iteration_activities or [])}
        try:
            # Create patch operations for each updated activity
            patch_ops: list[dict[str, Any]] = []

            for activity, old_values in updated_activities:
                # New per-iteration records get "add" ops (appended below), not "replace"
                if activity.activity_name in new_activity_names:
                    continue

                activity_idx = metadata.activity_index_map.get(activity.activity_name)
                if activity_idx is None:
                    logger.warning(
                        "Activity not found in activities list for execution",
                        activity_name=activity.activity_name,
                        execution_id=execution_id,
                    )
                    continue

                patch_ops.extend(self._build_field_patch_ops(activity, old_values, activity_idx))

            # Append "add" ops for new per-iteration records and iteration=0 patches for originals
            if new_iteration_activities:
                patch_ops.extend(self._build_iteration_patch_ops(new_iteration_activities, metadata.activity_index_map))

            # Publish patches if there are any operations
            if patch_ops:
                # Wrap operations in a JsonPatch object
                json_patch = JsonPatch(patch_ops)
                await self.activity_publisher.publish_activity_patch(execution_id, [json_patch])

                logger.debug(
                    "Published patch operations for execution (activities updated)",
                    operation_count=len(patch_ops),
                    execution_id=execution_id,
                    updated_activity_count=len(updated_activities),
                    new_iteration_count=len(new_iteration_activities or []),
                )

        except Exception:
            # Log error but don't fail database sync (publishing is best-effort)
            logger.exception("Failed to publish activity patches for execution (non-fatal)", execution_id=execution_id)
