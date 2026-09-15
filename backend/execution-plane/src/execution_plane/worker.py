"""Execution Plane TE worker — polls work_items and dispatches to Temporal on completion."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import asyncpg
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from temporalio.client import Client
from temporalio.exceptions import ApplicationError
from temporalio.service import RPCError, RPCStatusCode, TLSConfig

from execution_plane.models.work_item import WorkItem, WorkItemStatus
from execution_plane.script_executor import ScriptExecutionError, execute_script

logger = structlog.stdlib.get_logger(__name__)

POLL_INTERVAL_SECONDS = 5
NOTIFY_CHANNEL = "execution_plane_work_items"


async def _claim_pending_items(session: AsyncSession) -> list[WorkItem]:
    """SELECT ... FOR UPDATE SKIP LOCKED to claim pending work items."""
    result = await session.execute(
        select(WorkItem)
        .where(WorkItem.status == WorkItemStatus.PENDING)
        .order_by(WorkItem.created_at)
        .limit(10)
        .with_for_update(skip_locked=True)
    )
    items = list(result.scalars().all())
    for item in items:
        item.status = WorkItemStatus.CLAIMED
        item.claimed_at = datetime.now(UTC)
    if items:
        await session.commit()
    return items


async def _signal_temporal(item: WorkItem, session: AsyncSession, temporal_client: Client) -> None:
    """Call handle.complete() or handle.fail(), then set signaled_at.

    If Temporal returns NOT_FOUND the token was already consumed — the signal
    was delivered on a previous attempt. We still mark signaled_at so the
    recovery pass stops retrying this item.

    Any other RPC error is re-raised; signaled_at stays NULL so the startup
    recovery pass will retry on next boot.
    """
    wi_id = str(item.id)
    task_token = base64.b64decode(item.activity_handle)
    handle = temporal_client.get_async_activity_handle(task_token=task_token)

    try:
        if item.status == WorkItemStatus.COMPLETED:
            await handle.complete(item.result or {})
        else:
            result = item.result or {}
            error_msg = result.get("error", "Script execution failed")
            error_type = result.get("error_type", "ScriptExecutionError")
            await handle.fail(ApplicationError(error_msg, type=error_type, non_retryable=True))
    except RPCError as e:
        if e.status == RPCStatusCode.NOT_FOUND:
            logger.info("Temporal activity already completed, marking as signaled", work_item_id=wi_id)
        else:
            logger.warning(
                "Failed to signal Temporal, will retry on next recovery pass",
                work_item_id=wi_id,
                error=str(e),
            )
            return

    item.signaled_at = datetime.now(UTC)
    await session.commit()
    logger.info("Temporal signal delivered", work_item_id=wi_id, status=item.status)


async def _process_item(item: WorkItem, session: AsyncSession, temporal_client: Client) -> None:
    """Process one work item: execute script, persist result, then signal Temporal."""
    wi_id = str(item.id)
    input_config: dict = item.payload.get("input_config", {})
    output_config: dict | None = item.payload.get("output_config")

    # Step 1: Run the script.
    try:
        activity_result = await execute_script(input_config, output_config)
        item.result = activity_result
        item.status = WorkItemStatus.COMPLETED
        logger.info("Script executed successfully", work_item_id=wi_id)
    except ScriptExecutionError as e:
        item.result = {"error": str(e), "error_type": "ScriptExecutionError"}
        item.status = WorkItemStatus.FAILED
        logger.warning("Script execution failed", work_item_id=wi_id, error=str(e))
    except Exception as e:
        item.result = {"error": str(e), "error_type": type(e).__name__}
        item.status = WorkItemStatus.FAILED
        logger.exception("Unexpected error processing work item", work_item_id=wi_id)

    item.completed_at = datetime.now(UTC)

    # Step 2: Persist result before signaling — if the gRPC call is lost, the
    # startup recovery pass can retry using the result already in the DB.
    await session.commit()

    # Step 3: Signal Temporal. Sets signaled_at on success.
    await _signal_temporal(item, session, temporal_client)


async def _recover_undelivered(
    session_factory: async_sessionmaker[AsyncSession],
    temporal_client: Client,
) -> None:
    """Retry Temporal signals for items that completed but were never confirmed delivered.

    Runs once at startup. Bounded query: only items in a terminal state with a
    NULL signaled_at — items that finished between a crash and the previous
    graceful shutdown.
    """
    async with session_factory() as session:
        result = await session.execute(
            select(WorkItem)
            .where(WorkItem.status.in_([WorkItemStatus.COMPLETED, WorkItemStatus.FAILED]))
            .where(WorkItem.signaled_at.is_(None))
        )
        items = list(result.scalars().all())

    if not items:
        return

    logger.info("Recovering undelivered Temporal signals", count=len(items))
    for item in items:
        async with session_factory() as item_session:
            refreshed = await item_session.get(WorkItem, item.id)
            if refreshed:
                await _signal_temporal(refreshed, item_session, temporal_client)


async def _listen_loop(database_url: str, wakeup_event: asyncio.Event) -> None:
    """Hold a LISTEN connection; set wakeup_event on every NOTIFY.

    Known gap: a zombie TCP connection (NAT expiry, silent load-balancer drop,
    VM migration) will not trigger the termination listener, so the worker
    silently falls back to POLL_INTERVAL_SECONDS cadence until the OS-level
    TCP keepalive eventually kills the connection. Fix: periodic self-NOTIFY or
    a LISTEN/UNLISTEN probe to detect stale connections. See AAP-92715.
    """
    # asyncpg uses plain postgresql:// (not postgresql+asyncpg://)
    pg_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    while True:
        try:
            disconnected = asyncio.Event()
            conn: asyncpg.Connection = await asyncpg.connect(pg_url)
            try:
                conn.add_termination_listener(lambda _, ev=disconnected: ev.set())
                await conn.add_listener(NOTIFY_CHANNEL, lambda *_: wakeup_event.set())
                logger.info("Listening for notifications", channel=NOTIFY_CHANNEL)
                await disconnected.wait()
            finally:
                with contextlib.suppress(Exception):
                    await conn.close()
        except Exception:
            logger.exception("Notification listener failed, reconnecting in 5s")
            await asyncio.sleep(5)


async def _poll_loop(
    session_factory: async_sessionmaker[AsyncSession],
    temporal_client: Client,
    wakeup_event: asyncio.Event,
) -> None:
    """Poll for and process pending work items; wake immediately on pg_notify."""
    logger.info("Execution Plane worker started, polling for work items")
    wakeup_event.set()  # process any items already present at startup
    while True:
        try:
            async with session_factory() as session:
                items = await _claim_pending_items(session)
                if items:
                    logger.info("Claimed work items", count=len(items))
                for item in items:
                    async with session_factory() as item_session:
                        # Re-fetch so changes are tracked in this session
                        refreshed = await item_session.get(WorkItem, item.id)
                        if refreshed:
                            await _process_item(refreshed, item_session, temporal_client)
        except Exception:
            logger.exception("Error in polling loop, will retry")
        wakeup_event.clear()
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(wakeup_event.wait(), timeout=POLL_INTERVAL_SECONDS)


async def _create_temporal_client() -> Client:
    """Connect to Temporal using the same env vars as the Syntara worker."""
    temporal_address = os.environ.get("APP_TEMPORAL_ADDRESS", "localhost:7233")
    temporal_namespace = os.environ.get("APP_TEMPORAL_NAMESPACE", "default")

    tls: TLSConfig | None = None
    if os.environ.get("APP_S2S_TLS_ENABLED", "").lower() == "true":
        ca = os.environ.get("APP_S2S_TLS_CA_CERT_PATH")
        cert = os.environ.get("APP_S2S_TLS_CERT_PATH")
        key = os.environ.get("APP_S2S_TLS_KEY_PATH")
        if ca and cert and key:
            tls = TLSConfig(
                server_root_ca_cert=Path(ca).read_bytes(),
                client_cert=Path(cert).read_bytes(),
                client_private_key=Path(key).read_bytes(),
            )

    client = await Client.connect(temporal_address, namespace=temporal_namespace, tls=tls)
    logger.info(
        "Connected to Temporal",
        address=temporal_address,
        namespace=temporal_namespace,
        tls_enabled=tls is not None,
    )
    return client


async def _run() -> None:
    database_url = os.environ.get("APP_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL (or APP_DATABASE_URL) environment variable is required")
        sys.exit(1)

    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    temporal_client = await _create_temporal_client()

    await _recover_undelivered(session_factory, temporal_client)

    wakeup_event = asyncio.Event()
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(_listen_loop(database_url, wakeup_event), name="ep-listener")
            tg.create_task(_poll_loop(session_factory, temporal_client, wakeup_event), name="ep-poll")
    finally:
        await engine.dispose()


def main() -> None:
    """Entry point for the execution-plane-worker CLI command."""
    logging.basicConfig(level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    asyncio.run(_run())


if __name__ == "__main__":
    main()
