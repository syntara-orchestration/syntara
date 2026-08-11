"""Internal activity for workflow execution monitoring.

This module contains the register_activity_monitoring activity which is
automatically scheduled at the start of every workflow execution to enable
real-time activity syncing to the database.
"""

import asyncio
from uuid import UUID

import structlog
from sqlmodel import select
from temporalio import activity

from syntara.core.database.session import AsyncSessionLocal
from syntara.workflows.models.execution import Execution

# Import directly from registry module file to avoid triggering services/__init__.py
# which would cause circular import with temporal_worker
from syntara.workflows.workflow_engine.models.workflow_definition import ActivityName
from syntara.workflows.workflow_engine.services.activity_sync_registry import (
    get_activity_sync_service,
)

logger = structlog.stdlib.get_logger(__name__)


@activity.defn(name=ActivityName.ACTIVITY_MONITORING)
async def register_activity_monitoring(
    execution_id: str,
    temporal_workflow_id: str,
    request_id: str | None = None,
) -> None:
    """Register activity monitoring for a workflow execution.

    This internal activity is called at the start of every workflow execution
    to begin real-time activity syncing to the database. It runs outside the
    workflow sandbox and can perform I/O operations safely.

    This activity implements explicit retry with backoff to wait for the Execution
    record to be created in the database before starting monitoring. It also ensures
    that only one monitoring task per execution_id is scheduled.

    Args:
        execution_id: Database execution ID
        temporal_workflow_id: Temporal workflow ID
        request_id: Optional X-Request-Id (UUID) from the originating HTTP request

    Raises:
        RuntimeError: If activity sync service is not available
        Exception: If monitoring setup fails after all retries

    """
    sync_service = get_activity_sync_service()
    if not sync_service:
        msg = f"Activity sync service not available for execution {execution_id}"
        logger.error(msg)
        raise RuntimeError(msg)

    # Check if monitoring is already running for this execution
    if sync_service.is_monitoring_execution(UUID(execution_id)):
        logger.info("Activity monitoring already running for execution, skipping", execution_id=execution_id)
        return

    # Wait for Execution record to be created in DB with exponential backoff
    # This avoids logging unnecessary errors from retry_policy
    max_retries = 5
    base_delay = 0.5  # 500ms
    execution_uuid = UUID(execution_id)

    for attempt in range(max_retries):
        async with AsyncSessionLocal() as session:
            result = await session.exec(select(Execution).where(Execution.id == execution_uuid))
            execution = result.one_or_none()

            if execution:
                # Execution record found, start monitoring
                request_id_uuid = UUID(request_id) if request_id else None
                sync_service.start_monitoring_execution(
                    execution_uuid, temporal_workflow_id, request_id=request_id_uuid
                )
                logger.info("Activity monitoring registered for execution", execution_id=execution_id)
                return

        # Execution record not found yet, wait with exponential backoff
        if attempt < max_retries - 1:
            delay = base_delay * (2**attempt)
            logger.debug(
                "Execution not found in DB, retrying",
                execution_id=execution_id,
                delay=delay,
                attempt=attempt + 1,
                max_retries=max_retries,
            )
            await asyncio.sleep(delay)

    # All retries exhausted
    msg = f"Execution {execution_id} not found in database after {max_retries} retries"
    logger.error(msg)
    raise RuntimeError(msg)
