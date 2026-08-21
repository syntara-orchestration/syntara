"""Best-effort cancellation of agentic invocations linked to a workflow execution.

When a user cancels a workflow execution, Temporal cancels the workflow but
agentic activities have already exited via ``raise_complete_async()``.  The
running agent process is unaware of the Temporal cancel.  This module bridges
the gap by querying for active invocations that belong to the execution and
marking them as CANCELLED in the database.  The agent loop detects the status
change on its next DB poll and stops.
"""

from datetime import UTC, datetime
from uuid import UUID

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus

logger = structlog.stdlib.get_logger(__name__)

_CANCELLABLE_STATUSES = (InvocationStatus.CREATED, InvocationStatus.RUNNING)


async def find_active_invocations_for_execution(
    session: AsyncSession,
    execution_id: UUID,
) -> list[Invocation]:
    """Return invocations linked to *execution_id* that are still cancellable.

    Uses a JSONB query on ``context_data->>'execution_id'``.  This is not
    indexed but only runs on the cancel path so performance is acceptable.
    """
    result = await session.exec(
        select(Invocation).where(
            Invocation.context_data["execution_id"].as_string() == str(execution_id),  # type: ignore[index]
            col(Invocation.status).in_(_CANCELLABLE_STATUSES),
        )
    )
    return list(result.all())


async def cancel_invocations_for_execution(
    session: AsyncSession,
    execution_id: UUID,
    reason: str = "Workflow execution cancelled",
) -> int:
    """Cancel all active invocations belonging to *execution_id*.

    Each invocation is individually try/excepted so one failure does not
    block the others.  Returns the number of successfully cancelled
    invocations.
    """
    invocations = await find_active_invocations_for_execution(session, execution_id)
    if not invocations:
        logger.debug(
            "No active invocations to cancel for execution",
            execution_id=execution_id,
        )
        return 0

    logger.info(
        "Cancelling invocations for execution",
        execution_id=execution_id,
        count=len(invocations),
    )

    cancelled = 0
    now = datetime.now(UTC)
    for invocation in invocations:
        try:
            invocation.status = InvocationStatus.CANCELLED
            invocation.error_message = f"Workflow cancelled: {reason}"
            invocation.completed_at = now
            cancelled += 1
        except Exception:
            logger.exception(
                "Failed to mark invocation as cancelled",
                invocation_id=invocation.id,
                execution_id=execution_id,
            )

    if cancelled:
        try:
            await session.commit()
        except Exception:
            logger.exception(
                "Failed to commit invocation cancellations",
                execution_id=execution_id,
                attempted=cancelled,
            )
            return 0

    logger.info(
        "Invocation cancellation complete",
        execution_id=execution_id,
        cancelled=cancelled,
        total=len(invocations),
    )
    return cancelled
