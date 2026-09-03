"""Helpers for detecting invocation cancellation from a running agent."""

import asyncio
from uuid import UUID

import structlog
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.agent_orchestrator.exceptions import InvocationCancelledError
from syntara.agent_orchestrator.models.invocation import Invocation, InvocationStatus
from syntara.core.cache.stream import StreamClient
from syntara.core.database.session import AsyncSessionLocal

logger = structlog.stdlib.get_logger(__name__)

# StreamClient has no socket_timeout, so EXISTS can block forever. Bound it so a
# hung Redis is treated as unavailable and we fall back to the invocation row.
_REDIS_CANCEL_CHECK_TIMEOUT_SECONDS = 2.0


def get_invocation_cancel_key(invocation_id: UUID) -> str:
    """Get Redis key for an invocation's cancellation signal.

    Args:
        invocation_id: UUID of the invocation

    Returns:
        Redis key (e.g., "invocation:UUID:cancelled")

    """
    return f"invocation:{invocation_id}:cancelled"


async def is_invocation_cancelled(session: AsyncSession, invocation_id: UUID) -> bool:
    """Return True if *invocation_id* exists and is in CANCELLED status."""
    invocation = await session.get(Invocation, invocation_id)
    return invocation is not None and invocation.status == InvocationStatus.CANCELLED


async def raise_if_invocation_cancelled(invocation_id: UUID, phase: str) -> None:
    """Raise ``InvocationCancelledError`` if the invocation was cancelled.

    Redis-first (cancel key), with a DB fallback only when Redis itself errors
    or the EXISTS check exceeds ``_REDIS_CANCEL_CHECK_TIMEOUT_SECONDS``.
    Database errors are logged and swallowed so a failed status check cannot
    take down an otherwise healthy agent run.
    """
    cancelled = False
    redis_available = True

    try:
        async with StreamClient() as client:
            cancelled = (
                await asyncio.wait_for(
                    client.key_exists(get_invocation_cancel_key(invocation_id)),
                    timeout=_REDIS_CANCEL_CHECK_TIMEOUT_SECONDS,
                )
                is True
            )
    except Exception:  # noqa: BLE001
        redis_available = False
        logger.debug(
            "Redis cancellation check failed, falling back to DB",
            invocation_id=invocation_id,
        )

    if not redis_available and not cancelled:
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
