"""Execution Plane TE worker — polls work_items and dispatches to Temporal on completion."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from execution_plane.config import get_ep_settings
from execution_plane.models.work_item import WorkItem, WorkItemStatus
from execution_plane.script_executor import ScriptExecutionError, execute_script
from execution_plane.temporal_client import send_temporal_callback
from execution_plane.work_store import WorkStore

logger = structlog.stdlib.get_logger(__name__)

POLL_INTERVAL_SECONDS = 5
NOTIFY_CHANNEL = "execution_plane_work_items"


CompletionCallback = Callable[[WorkItem], Awaitable[bool]]


async def _process_item(item: WorkItem, store: WorkStore, completion_callback: CompletionCallback) -> None:
    """Execute script, persist result, then send Temporal callback."""
    wi_id = str(item.id)
    input_config: dict[str, Any] = item.payload.get("input_config", {})
    output_config: dict[str, str] | None = item.payload.get("output_config")

    try:
        activity_result = await execute_script(input_config, output_config)
        await store.set_result(item, activity_result, WorkItemStatus.COMPLETED)
        logger.info("Script executed successfully", work_item_id=wi_id)
    except ScriptExecutionError as e:
        await store.set_result(
            item,
            {
                "error": str(e),
                "error_type": "ScriptExecutionError",
                "exit_code": e.exit_code,
                "stdout": e.stdout,
                "stderr": e.stderr,
            },
            WorkItemStatus.FAILED,
        )
        logger.warning("Script execution failed", work_item_id=wi_id, error=str(e))
    except Exception as e:
        await store.set_result(item, {"error": str(e), "error_type": type(e).__name__}, WorkItemStatus.FAILED)
        logger.exception("Unexpected error processing work item", work_item_id=wi_id)

    if await completion_callback(item):
        await store.mark_signal_delivered(item)


async def _recover_undelivered(
    session_factory: async_sessionmaker[AsyncSession], completion_callback: CompletionCallback
) -> None:
    """Retry callbacks for items that completed but were never confirmed delivered.

    Runs once at startup. Bounded query: only terminal items with NULL signaled_at.
    All recovery happens in a single session — no re-fetch needed.
    """
    async with session_factory() as session:
        store = WorkStore(session)
        items = await store.find_undelivered()
        if not items:
            return
        logger.info("Recovering undelivered Temporal callbacks", count=len(items))
        for item in items:
            if await completion_callback(item):
                await store.mark_signal_delivered(item)


async def _listen_loop(database_url: str, wakeup_event: asyncio.Event) -> None:
    """Hold a LISTEN connection; set wakeup_event on every NOTIFY.

    Known gap: a zombie TCP connection (NAT expiry, silent load-balancer drop,
    VM migration) will not trigger the termination listener, so the worker
    silently falls back to POLL_INTERVAL_SECONDS cadence until the OS-level
    TCP keepalive eventually kills the connection. Fix: periodic self-NOTIFY or
    a LISTEN/UNLISTEN probe to detect stale connections. See AAP-92715.
    """
    while True:
        try:
            disconnected = asyncio.Event()
            conn: asyncpg.Connection = await asyncpg.connect(database_url)
            try:
                conn.add_termination_listener(lambda _, ev=disconnected: ev.set())
                await conn.add_listener(NOTIFY_CHANNEL, lambda *_: wakeup_event.set())
                # Recheck work queued before LISTEN became active (also on reconnect).
                wakeup_event.set()
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
    wakeup_event: asyncio.Event,
    completion_callback: CompletionCallback,
) -> None:
    """Claim one work item at a time; sleep between polls when queue is empty."""
    logger.info("Execution Plane worker started, polling for work items")
    wakeup_event.set()  # process any items already present at startup
    while True:
        item = None
        try:
            async with session_factory() as session:
                store = WorkStore(session)
                item = await store.claim_one()
                if item:
                    logger.info("Claimed work item", work_item_id=str(item.id))
                    await _process_item(item, store, completion_callback)
        except Exception:
            logger.exception("Error in polling loop, will retry")

        if not item:
            wakeup_event.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(wakeup_event.wait(), timeout=POLL_INTERVAL_SECONDS)


async def run_worker(
    session_factory: async_sessionmaker[AsyncSession],
    database_url: str,
    completion_callback: CompletionCallback = send_temporal_callback,
) -> None:
    """Run processing until cancelled, using the supplied database and callback.

    The caller owns the session factory's engine. Cancellation closes both the
    notification listener and the polling task before returning to the caller.
    """
    await _recover_undelivered(session_factory, completion_callback)
    wakeup_event = asyncio.Event()
    async with asyncio.TaskGroup() as tg:
        tg.create_task(_listen_loop(database_url, wakeup_event), name="ep-listener")
        tg.create_task(_poll_loop(session_factory, wakeup_event, completion_callback), name="ep-poll")


async def _run() -> None:
    settings = get_ep_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    try:
        await run_worker(session_factory, settings.database_url_asyncpg)
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
