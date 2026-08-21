"""Helpers for detecting invocation cancellation from a running agent."""

from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.exceptions import InvocationCancelledError
from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.core.database.session import AsyncSessionLocal

logger = structlog.stdlib.get_logger(__name__)


async def is_invocation_cancelled(session: AsyncSession, invocation_id: UUID) -> bool:
    """Return True if *invocation_id* exists and is in CANCELLED status."""
    invocation = await session.get(Invocation, invocation_id)
    return invocation is not None and invocation.status == InvocationStatus.CANCELLED


async def raise_if_invocation_cancelled(invocation_id: UUID, phase: str) -> None:
    """Raise ``InvocationCancelledError`` if the invocation was cancelled.

    Database errors are logged and swallowed so a failed status check cannot
    take down an otherwise healthy agent run.
    """
    try:
        async with AsyncSessionLocal() as session:
            cancelled = await is_invocation_cancelled(session, invocation_id)
    except (SQLAlchemyError, OSError) as exc:
        logger.warning(
            "Failed to check cancellation status for invocation, continuing execution",
            invocation_id=invocation_id,
            error=str(exc),
            exc_info=True,
        )
        return

    if cancelled:
        raise InvocationCancelledError(str(invocation_id), phase)
