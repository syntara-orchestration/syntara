"""Retry output resolution activity for retry-from-failure.

When an execution is retried from a failure point, the nodes upstream of that
point are skipped and the workflow needs their stored ``output_data`` injected
into the execution namespace so downstream nodes read them as if those nodes had
just run.

The outputs are not carried in ``start_workflow`` arguments. They reach the
workflow through this activity instead, following the same rule the credential
and integration resolution activities already use: the definition carries an
identifier, the data is fetched at the point of use, and it is never allowed to
linger in workflow state. Two reasons:

* **Payload size.** ``DEFAULT_MAX_OUTPUT_BYTES`` is 1 MiB per activity against
  Temporal's 2 MiB blob limit, so a retry skipping two large nodes would overflow
  the arguments blob. Per commit 5959f5b79 the SDK does not mark a size rejection
  non-retryable, so the overflow surfaces as futile retries until activity
  timeout with a misleading "Activity task timed out" error.
* **History growth.** Workflow state is persisted in history, so leaving every
  restored output resident inflates every later history entry.

The workflow scrubs each node's output from state immediately after dispatching
or skipping that node, mirroring ``DynamicWorkflow._scrub_activity_credentials``.
"""

from typing import Any

import structlog
from sqlmodel import select
from temporalio import activity, workflow

with workflow.unsafe.imports_passed_through():
    from syntara.core.constants import JsonbLimits
    from syntara.core.database.session import get_db
    from syntara.core.exceptions import SafeValueError
    from syntara.workflows.models.activity_execution import ActivityExecution, ActivityStatus
    from syntara.workflows.utils.loop_iteration_names import strip_iteration_suffix

logger = structlog.stdlib.get_logger(__name__)


@activity.defn(name="fetch_retry_outputs")
async def fetch_retry_outputs_activity(
    source_execution_id: str,
    node_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """Fetch stored outputs for nodes a retry will skip.

    Args:
        source_execution_id: Execution whose ``ActivityExecution`` rows hold the
            outputs to restore.
        node_ids: Canvas node ids to fetch. Loop-iteration-suffixed ids are
            accepted and resolved to their base node.

    Returns:
        Map of node id to the output of its most recent ``COMPLETED`` activity
        in the source run. Nodes with no completed activity are absent from the
        map rather than mapped to an empty output, so the caller can tell
        "nothing ran" apart from "ran and produced nothing".

    Raises:
        SafeValueError: If the combined serialized size would exceed
            ``JsonbLimits.MAX_FIELD_BYTES``, which would overflow the activity
            result blob. Raised rather than truncated because a silently
            truncated output is worse than a refused retry.

    """
    if not node_ids:
        return {}

    wanted = {strip_iteration_suffix(node_id.strip()) for node_id in node_ids if node_id and node_id.strip()}
    if not wanted:
        return {}

    outputs: dict[str, dict[str, Any]] = {}
    async for session in get_db():
        activities = (
            await session.exec(
                select(ActivityExecution).where(
                    ActivityExecution.execution_id == source_execution_id,
                    ActivityExecution.status == ActivityStatus.COMPLETED,
                )
            )
        ).all()
        # Ids are matched on the base node id, so a loop node resolves to the
        # most recent completed iteration. Per-iteration granularity is
        # classification's concern, not the transport's.
        for activity_row in activities:
            base_id = strip_iteration_suffix(activity_row.activity_name)
            if base_id in wanted:
                outputs[base_id] = activity_row.output_data or {}

    serialized_bytes = sum(len(str(output)) for output in outputs.values())
    if serialized_bytes > JsonbLimits.MAX_FIELD_BYTES:
        msg = (
            f"restored retry outputs total {serialized_bytes} bytes across {len(outputs)} node(s), "
            f"over the {JsonbLimits.MAX_FIELD_BYTES} byte maximum. This retry cannot restore the "
            "upstream outputs it needs in order to skip those nodes."
        )
        raise SafeValueError(msg)

    logger.info(
        "Fetched retry outputs",
        source_execution_id=source_execution_id,
        node_count=len(outputs),
        serialized_bytes=serialized_bytes,
    )
    return outputs
