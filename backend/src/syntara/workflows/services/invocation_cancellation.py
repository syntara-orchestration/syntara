"""Best-effort cancellation of agentic invocations linked to a workflow execution.

When a user cancels a workflow execution, Temporal cancels the workflow but
agentic activities have already exited via ``raise_complete_async()``.  The
running agent process is unaware of the Temporal cancel.  This module finds
active invocations for the execution and cancels them through
``InvocationService`` (audit events, file cleanup, conditional status update,
Redis cancel signal). The running agent stops via the Redis watcher, with a
DB status fallback when Redis is unavailable.
"""

from uuid import UUID

import structlog
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.agent_orchestrator.models.request import CancellationResult
from syntara.agent_orchestrator.services.invocation_service import InvocationService
from syntara.core.models import User

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
            Invocation.context_data["execution_id"].as_string() == str(execution_id),  # type: ignore[attr-defined]
            col(Invocation.status).in_(_CANCELLABLE_STATUSES),
        )
    )
    return list(result.all())


async def cancel_invocations_for_execution(
    session: AsyncSession,
    user: User,
    execution_id: UUID,
    reason: str = "Workflow execution cancelled",
) -> int:
    """Cancel all active invocations belonging to *execution_id*.

    Each invocation is cancelled via ``InvocationService`` so one failure does
    not block the others.  Returns the number of successfully cancelled
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

    service = InvocationService(session, user)
    cancelled = 0
    for invocation in invocations:
        try:
            result = await service.cancel_invocation(invocation.id, reason)
            if result == CancellationResult.SUCCESS:
                cancelled += 1
        except Exception:
            logger.exception(
                "Failed to cancel invocation for execution",
                invocation_id=invocation.id,
                execution_id=execution_id,
            )
            try:
                await session.rollback()
            except Exception:
                logger.exception(
                    "Failed to rollback after invocation cancel error",
                    invocation_id=invocation.id,
                    execution_id=execution_id,
                )

    logger.info(
        "Invocation cancellation complete",
        execution_id=execution_id,
        cancelled=cancelled,
        total=len(invocations),
    )
    return cancelled
