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
from syntara.workflows.models.activity_execution import ActivityExecution
from syntara.workflows.models.execution import Execution

logger = structlog.stdlib.get_logger(__name__)

_CANCELLABLE_STATUSES = (InvocationStatus.CREATED, InvocationStatus.RUNNING)


async def linked_invocation_ids(session: AsyncSession, execution_id: UUID) -> list[UUID]:
    """Invocation ids this execution's agentic activities reported.

    Read from ``ActivityExecution.output_data``, which the activity-sync service
    writes from the worker's Temporal heartbeat. Unlike
    ``Invocation.context_data`` — accepted verbatim from the invocation-create
    request, so any caller can put an arbitrary ``execution_id`` in it — this is
    not caller-writable, and it is already scoped to this execution by foreign
    key. Using it keeps one tenant's cancellation from reaching another tenant's
    invocation. Ref: AAP-88614.
    """
    result = await session.exec(
        select(col(ActivityExecution.output_data)["invocation_id"].astext).where(
            ActivityExecution.execution_id == execution_id,
            col(ActivityExecution.output_data)["invocation_id"].isnot(None),
        )
    )

    invocation_ids: list[UUID] = []
    for raw_id in result.all():
        try:
            invocation_ids.append(UUID(raw_id))
        except (AttributeError, TypeError, ValueError):
            logger.warning(
                "Ignoring malformed invocation_id in activity output",
                execution_id=execution_id,
                value=raw_id,
            )
    return invocation_ids


async def find_active_invocations_for_execution(
    session: AsyncSession,
    execution_id: UUID,
) -> list[Invocation]:
    """Return invocations linked to *execution_id* that are still cancellable.

    Invocations are loaded by primary key from the activity-output link and
    filtered to the cancelled execution's project, so the lookup cannot reach
    another tenant's invocation even if the link were somehow wrong.
    """
    invocation_ids = await linked_invocation_ids(session, execution_id)
    if not invocation_ids:
        return []

    project_id = select(Execution.project_id).where(Execution.id == execution_id).scalar_subquery()

    result = await session.exec(
        select(Invocation).where(
            col(Invocation.id).in_(invocation_ids),
            Invocation.project_id == project_id,
            col(Invocation.status).in_(_CANCELLABLE_STATUSES),
        )
    )
    return list(result.all())


async def cancel_invocations_for_execution(
    session: AsyncSession,
    user: User,
    execution_id: UUID,
    reason: str = "Workflow execution cancelled",
) -> list[UUID]:
    """Cancel all active invocations belonging to *execution_id*.

    Each invocation is cancelled via ``InvocationService`` so one failure does
    not block the others.  Returns the ids of the successfully cancelled
    invocations, so the caller can follow up on exactly those.
    """
    invocations = await find_active_invocations_for_execution(session, execution_id)
    if not invocations:
        logger.debug(
            "No active invocations to cancel for execution",
            execution_id=execution_id,
        )
        return []

    logger.info(
        "Cancelling invocations for execution",
        execution_id=execution_id,
        count=len(invocations),
    )

    service = InvocationService(session, user)
    cancelled: list[UUID] = []
    for invocation in invocations:
        try:
            result = await service.cancel_invocation(invocation.id, reason)
            if result == CancellationResult.SUCCESS:
                cancelled.append(invocation.id)
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
        cancelled=len(cancelled),
        total=len(invocations),
    )
    return cancelled
