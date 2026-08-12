"""Periodic cleanup of expired and revoked refresh sessions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from sqlalchemy import text

from syntara.core.database.session import AsyncSessionLocal
from syntara.core.workers.periodic import PeriodicWorker

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)

_CLEANUP_BATCH_SIZE = 1000
_CLEANUP_MAX_BATCHES = 100
_REVOKE_GRACE_PERIOD_MINUTES = 5


_CLEANUP_EXPIRED_SQL = """
    DELETE FROM refresh_sessions
    WHERE jti IN (
        SELECT jti FROM refresh_sessions
        WHERE expires_at < NOW()
        LIMIT :batch_size
    )
"""

_CLEANUP_REVOKED_SQL = """
    DELETE FROM refresh_sessions
    WHERE jti IN (
        SELECT jti FROM refresh_sessions
        WHERE revoked_at IS NOT NULL
          AND revoked_at < NOW() - MAKE_INTERVAL(mins => :grace_minutes)
        LIMIT :batch_size
    )
"""


async def cleanup_expired_sessions(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Delete expired and revoked sessions in batches to avoid long-running transactions."""
    queries_and_params: list[tuple[str, dict[str, int]]] = [
        (_CLEANUP_EXPIRED_SQL, {"batch_size": _CLEANUP_BATCH_SIZE}),
        (_CLEANUP_REVOKED_SQL, {"batch_size": _CLEANUP_BATCH_SIZE, "grace_minutes": _REVOKE_GRACE_PERIOD_MINUTES}),
    ]
    total_deleted = 0
    async with session_factory() as session:
        for query, params in queries_and_params:
            for _ in range(_CLEANUP_MAX_BATCHES):
                result = await session.exec(text(query), params=params)  # type: ignore[call-overload]
                deleted = result.rowcount
                if deleted:
                    await session.commit()
                    total_deleted += deleted
                if deleted < _CLEANUP_BATCH_SIZE:
                    break
            else:
                logger.warning("session_cleanup_hit_cap", deleted_so_far=total_deleted)
    if total_deleted:
        logger.info("session_cleanup_completed", sessions_deleted=total_deleted)


def get_session_cleanup_worker() -> PeriodicWorker:
    """Create the periodic session cleanup worker."""
    return PeriodicWorker(
        name="session-cleanup",
        interval_seconds=3600,
        session_factory=AsyncSessionLocal,
        callback=cleanup_expired_sessions,
        coordinate=True,
    )
