"""Reconcile EP clusters from committed AO integration configuration."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import func
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from syntara.core.config.base import get_settings
from syntara.core.database.session import AsyncSessionLocal
from syntara.core.workers.periodic import PeriodicWorker, derive_lock_key
from syntara.execution_plane.cluster_sync_commands import apply_integration_cluster
from syntara.integrations.models.integration import Integration, IntegrationType

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from uuid import UUID

logger = structlog.stdlib.get_logger(__name__)
RECONCILIATION_NAME = "execution-plane-cluster-reconciliation"
_BATCH_SIZE = 50


@asynccontextmanager
async def _reconciliation_lock(session_factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[bool]:
    """Coordinate scheduled, manual, and immediate runs with the same transaction lock."""
    async with session_factory() as session:
        result = await session.exec(select(func.pg_try_advisory_xact_lock(derive_lock_key(RECONCILIATION_NAME))))
        yield bool(result.one())


async def _integration_batches(
    session_factory: async_sessionmaker[AsyncSession],
    integration_id: UUID | None,
) -> AsyncIterator[list[UUID]]:
    previous_id: UUID | None = None
    while True:
        query = select(Integration.id).where(Integration.integration_type == IntegrationType.OPENSHIFT)
        if integration_id is not None:
            query = query.where(Integration.id == integration_id)
        if previous_id is not None:
            query = query.where(col(Integration.id) > previous_id)
        async with session_factory() as session:
            rows = list((await session.exec(query.order_by(col(Integration.id)).limit(_BATCH_SIZE))).all())
        if not rows:
            return
        yield rows
        previous_id = rows[-1]


async def reconcile_integration_clusters(
    session_factory: async_sessionmaker[AsyncSession] | None,
    integration_id: UUID | None = None,
) -> dict[str, int]:
    """Attempt each current integration once; failures leave desired state available for the next run."""
    summary = {"synced": 0, "failed": 0, "skipped": 0}
    if session_factory is None:
        summary["failed"] = 1
        return summary
    try:
        async with _reconciliation_lock(session_factory) as acquired:
            if not acquired:
                summary["skipped"] = 1
                return summary
            async for batch in _integration_batches(session_factory, integration_id):
                for current_id in batch:
                    try:
                        async with asyncio.timeout(get_settings().ep_request_timeout_seconds):
                            applied = await apply_integration_cluster(session_factory, current_id)
                    except Exception as exc:  # noqa: BLE001 — isolate each integration's reconciliation failure
                        summary["failed"] += 1
                        logger.warning(
                            "ep_cluster_reconciliation_failed",
                            integration_id=str(current_id),
                            error_type=type(exc).__name__,
                        )
                    else:
                        summary["synced" if applied else "skipped"] += 1
            if integration_id is not None and not any(summary.values()):
                summary["failed"] = 1
                logger.warning("ep_cluster_reconciliation_missing_integration", integration_id=str(integration_id))
    except Exception as exc:  # noqa: BLE001 — post-commit delivery must not invalidate AO persistence
        summary["failed"] += 1
        logger.warning("ep_cluster_reconciliation_cycle_failed", error_type=type(exc).__name__)
    logger.info("ep_cluster_reconciliation_completed", **summary)
    return summary


async def reconcile_saved_integration(session: AsyncSession, integration: Integration) -> None:
    """Make one best-effort attempt after the request's configuration transaction committed."""
    if integration.integration_type != IntegrationType.OPENSHIFT:
        return
    session_factory = async_sessionmaker(session.bind, class_=AsyncSession, expire_on_commit=False)
    await reconcile_integration_clusters(session_factory, integration.id)


def get_cluster_reconciliation_worker() -> PeriodicWorker:
    """Use core coordination so manual and immediate runs share the scheduled run's lock."""
    return PeriodicWorker(
        name=RECONCILIATION_NAME,
        interval_seconds=get_settings().ep_cluster_reconciliation_interval_seconds,
        session_factory=AsyncSessionLocal,
        callback=reconcile_integration_clusters,
        coordinate=False,
    )
