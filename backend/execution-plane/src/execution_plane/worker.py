"""Execution Plane TE worker — polls work_items and dispatches to Temporal on completion."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

import asyncpg
import structlog

from execution_plane.config import get_ep_settings, to_asyncpg_url
from execution_plane.models.work_item import WorkItem, WorkItemStatus
from execution_plane.script_executor import ScriptExecutionError, execute_script
from execution_plane.services import ExecutionTargetRegistry
from execution_plane.temporal_client import send_temporal_callback
from execution_plane.work_store import WorkStore
from execution_plane.worker_manager import create_worker_manager
from execution_plane.worker_manager.base import WorkerDispatchError
from execution_plane.workflow_result import WorkflowResultError, normalize_workflow_result

logger = structlog.stdlib.get_logger(__name__)

POLL_INTERVAL_SECONDS = 5
NOTIFY_CHANNEL = "execution_plane_work_items"


CompletionCallback = Callable[[WorkItem], Awaitable[bool]]


async def _execute_cold_start(item: WorkItem, store: WorkStore) -> dict[str, Any]:
    """Resolve a target and dispatch one cold-start work item."""
    async with store.read_session() as session:
        registry = ExecutionTargetRegistry(session)
        target_id = item.payload.get("execution_target_id")
        if target_id is not None:
            try:
                target = await registry.find_active_by_id(uuid.UUID(str(target_id)))
            except ValueError as exc:
                msg = "execution_target_id must be a UUID"
                raise WorkerDispatchError(msg) from exc
        else:
            selector = item.payload.get("target_selector", {})
            if not isinstance(selector, dict):
                msg = "target_selector must be an object"
                raise WorkerDispatchError(msg)
            target = await registry.find_matching(selector)
    if target is None:
        msg = "no active execution target matches the requested labels"
        raise WorkerDispatchError(msg)
    await store.mark_dispatched(item.id, target.id)
    return await create_worker_manager(target).dispatch(item)


async def _process_item(item: WorkItem, store: WorkStore, completion_callback: CompletionCallback) -> None:
    """Execute locally or on a cold-start target, persist, then callback."""
    wi_id = str(item.id)
    input_config: dict[str, Any] = item.payload.get("input_config", {})
    output_config: dict[str, str] | None = item.payload.get("output_config")

    try:
        if "task_definition" in item.payload:
            activity_result = await _execute_cold_start(item, store)
            node_type = item.payload.get("workflow_node_type")
            if node_type is not None:
                activity_result = normalize_workflow_result(node_type, activity_result, output_config)
        else:
            activity_result = await execute_script(input_config, output_config)
        item = await store.set_result(item.id, activity_result, WorkItemStatus.COMPLETED)
        logger.info("Work item executed successfully", work_item_id=wi_id)
    except WorkflowResultError as e:
        item = await store.set_result(
            item.id,
            {
                "error": str(e),
                "error_type": e.error_type,
                "non_retryable": e.non_retryable,
                "details": e.details,
            },
            WorkItemStatus.FAILED,
        )
        logger.warning("Workflow node failed", work_item_id=wi_id, error_type=e.error_type)
    except ScriptExecutionError as e:
        item = await store.set_result(
            item.id,
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
    except WorkerDispatchError as e:
        item = await store.set_result(item.id, {"error": str(e), "error_type": type(e).__name__}, WorkItemStatus.FAILED)
        logger.warning("Work item execution failed", work_item_id=wi_id, error=str(e))
    except Exception as e:
        item = await store.set_result(
            item.id,
            {"error": str(e), "error_type": type(e).__name__},
            WorkItemStatus.FAILED,
        )
        logger.exception("Unexpected error processing work item", work_item_id=wi_id)

    if item.activity_handle is None or await completion_callback(item):
        await store.mark_signal_delivered(item.id)


async def _recover_undelivered(store: WorkStore, completion_callback: CompletionCallback) -> None:
    """Retry callbacks for items that completed but were never confirmed delivered.

    Runs once at startup. Bounded query: only terminal items with NULL signaled_at.
    Each store operation owns its own short-lived session.
    """
    items = await store.find_undelivered()
    if not items:
        return
    logger.info("Recovering undelivered Temporal callbacks", count=len(items))
    for item in items:
        if item.activity_handle is None or await completion_callback(item):
            await store.mark_signal_delivered(item.id)


async def _listen_loop(database_url: str, wakeup_event: asyncio.Event) -> None:
    """Hold a LISTEN connection and set the wakeup_event on every NOTIFY.

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
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Notification listener failed, reconnecting in 5s")
            await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _poll_loop(
    store: WorkStore,
    wakeup_event: asyncio.Event,
    completion_callback: CompletionCallback,
) -> None:
    """Claim one work item at a time; sleep between polls when queue is empty."""
    logger.info("Execution Plane worker started, polling for work items")
    wakeup_event.set()  # process any items already present at startup
    while True:
        item = None
        try:
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
    database_url: str,
    completion_callback: CompletionCallback = send_temporal_callback,
) -> None:
    """Run processing until cancelled, using the supplied database and callback.

    Cancellation closes both the notification listener and the polling task
    before returning to the caller, then disposes the store's engine.
    """
    async with WorkStore(database_url) as store:
        await _recover_undelivered(store, completion_callback)
        wakeup_event = asyncio.Event()
        async with asyncio.TaskGroup() as tg:
            tg.create_task(
                _listen_loop(to_asyncpg_url(database_url), wakeup_event),
                name="ep-listener",
            )
            tg.create_task(_poll_loop(store, wakeup_event, completion_callback), name="ep-poll")


async def _run() -> None:
    settings = get_ep_settings()
    await run_worker(settings.database_url)


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
