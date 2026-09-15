"""Script activity executors for bash and Python.

This module provides functionality to execute bash and Python scripts as workflow activities.
Scripts run in isolated subprocesses with timeout and error handling.
"""

import base64
import uuid
from datetime import UTC, datetime
from typing import Any

from execution_plane.models.work_item import WorkItem, WorkItemStatus
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from temporalio import activity
from temporalio.exceptions import ApplicationError

from syntara.core.config.base import get_settings
from syntara.workflows.workflow_engine.models.workflow_definition import (
    ActivityName,
    ScriptExecutorParameters,
)

from .common import HEARTBEAT_STOP_MONITOR


# Extraction boundary: execution_plane is a candidate for an independent service.
# The top-level execution_plane imports (WorkItem, WorkItemStatus, ScriptExecutionError,
# and the script execution utilities from script_executor) are the seam between
# Syntara and the EP. _dispatch_to_te and execute_script_activity's inline path
# are also part of that seam; if execution_plane becomes standalone they move out with it.
async def _dispatch_to_te(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> None:
    """Write a WorkItem to the execution_plane schema for TE worker pickup.

    Stores the Temporal async completion task token and script parameters
    so the TE worker can execute the script and signal Temporal on completion.
    """
    task_token_bytes: bytes = activity.info().task_token
    task_token_b64 = base64.b64encode(task_token_bytes).decode("ascii")
    execution_id_str = activity.info().workflow_id

    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        execution_id = uuid.UUID(execution_id_str) if execution_id_str else uuid.uuid4()
    except ValueError:
        execution_id = uuid.uuid4()

    work_item = WorkItem(
        id=uuid.uuid4(),
        execution_id=execution_id,
        activity_handle=task_token_b64,
        status=WorkItemStatus.PENDING,
        payload={"input_config": input_config, "output_config": output_config},
        created_at=datetime.now(UTC),
    )

    async with session_factory() as session:
        session.add(work_item)
        # pg_notify is transactional — delivered to listeners only after this commit
        await session.execute(text("SELECT pg_notify('execution_plane_work_items', '')"))
        await session.commit()

    await engine.dispose()
    activity.logger.info("Dispatched work item to TE work_item_id=%s", work_item.id)


@activity.defn(name=ActivityName.SCRIPT)
async def execute_script_activity(
    input_config: dict[str, Any],
    output_config: dict[str, str] | None,
) -> dict[str, Any]:
    """Dispatch a script execution request to the Execution Plane TE worker.

    SECURITY: Script nodes execute arbitrary user-supplied code (bash/Python)
    directly in the TE worker process without additional sandboxing. Enabling this
    grants any user with workflow:create + execution:run permissions the ability
    to run arbitrary commands on the worker infrastructure.
    Enabling Script Node is not recommended for production deployments.

    Validates the config eagerly (before writing the work item) so bad configs
    are rejected at submission time with a clear error rather than silently
    failing inside the TE worker. Actual execution happens asynchronously: this
    activity writes a WorkItem row and returns via Temporal async completion
    once the TE worker signals the result.

    Args:
        input_config: Script configuration (already template-resolved in V2)
        output_config: Output mapping configuration

    """
    activity.heartbeat({HEARTBEAT_STOP_MONITOR: True})

    if not get_settings().script_nodes_enabled:
        msg = "Script node execution is not enabled."
        raise ApplicationError(msg, type="ScriptNodeDisabled", non_retryable=True)

    # Validate config before writing the work item to catch bad input early.
    try:
        ScriptExecutorParameters.model_validate(input_config)
    except Exception:  # noqa: BLE001
        msg = "Script activity configuration validation failed"
        raise ApplicationError(msg, type="ConfigError", non_retryable=True) from None

    await _dispatch_to_te(input_config, output_config)
    activity.raise_complete_async()
