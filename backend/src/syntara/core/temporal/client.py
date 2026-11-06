"""Shared Temporal client with connection caching.

Provides a single cached :class:`temporalio.client.Client` instance for
use across the application.  The client connects once and is reused; call
:func:`invalidate_client` on connection-level errors so the next
:func:`get_shared_client` call reconnects automatically.

The connect strategy is hardened against hangs and races:

* ``Client.connect`` runs *outside* ``_client_lock`` as a shared task, so
  a hung connect cannot block callers from taking the lock (lock convoy).
* Waiters join the in-flight connect via ``asyncio.shield`` with a bounded
  wait: a timeout returns ``None`` to that waiter only and leaves the
  connect running so overlapping waiters can still receive it.
* A new wait replaces ``_connect_task`` when the current one is older than
  the waiter budget, without cancelling waiters still joined to the
  previous task.
* Replaced connects are held in a strong-ref set until they finish so
  CPython's GC cannot cancel a still-pending ``Client.connect``; a late
  success that loses the race to another client is closed.

Workers are **not** routed through this module because they require a
custom ``DataConverter`` / ``CredentialPayloadCodec`` for payload
encryption.
"""

from __future__ import annotations

import asyncio
import time

import structlog
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from syntara.core.config.base import get_settings
from syntara.core.tls.temporal import build_temporal_tls_config
from syntara.workflows.workflow_engine.client_interceptor import WorkflowAuthClientInterceptor

logger = structlog.stdlib.get_logger(__name__)

CONNECTION_ERRORS: frozenset[RPCStatusCode] = frozenset(
    {RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED},
)

# Waiters bound how long they join an in-flight connect. A timeout returns
# None to that waiter only; the connect keeps running so overlapping waiters
# can still receive it. A new wait replaces ``_connect_task`` when the
# current one is older than this budget, without cancelling waiters still
# joined to the previous task.
CONNECT_TIMEOUT_SECONDS = 10.0

_client_lock = asyncio.Lock()
_cached_client: Client | None = None
_connect_task: asyncio.Task[Client | None] | None = None
_connect_started_at: float | None = None

# Strong refs so the event loop does not GC an in-flight connect task.
# ``asyncio.create_task`` keeps only a weak reference, and ``_connect_task``
# holds a strong one only while the task is current. When a stale connect is
# replaced (older than the waiter budget) the previous task would otherwise
# be referenced solely by waiters still in ``asyncio.shield``; once they time
# out nothing holds it and CPython GC-cancels ``Client.connect`` ("Task was
# destroyed but it is pending"), dropping a late success. This set keeps
# every connect alive until it finishes so a replaced connect can still
# cache its client.
_pending_connect_tasks: set[asyncio.Task[Client | None]] = set()


def _on_connect_task_done(task: asyncio.Task[Client | None]) -> None:
    """Drop the strong ref once a shared connect finishes."""
    _pending_connect_tasks.discard(task)


def _should_start_shared_connect(now: float) -> bool:
    """Return True when a new wait should start a connect task.

    Caller must hold ``_client_lock``. Replacing ``_connect_task`` does not
    cancel the previous task; waiters already joined to it keep awaiting
    that result.
    """
    if _connect_task is None or _connect_task.done():
        return True
    if _connect_started_at is None:
        return True
    return now - _connect_started_at >= CONNECT_TIMEOUT_SECONDS


def _start_shared_connect_locked(now: float) -> asyncio.Task[Client | None]:
    """Start a new shared connect. Caller must hold ``_client_lock``.

    The new task is tracked in ``_pending_connect_tasks`` so replacing a stale
    ``_connect_task`` does not leave the previous connect without a strong
    reference (which would let CPython GC-cancel it once its waiters time out).
    """
    global _connect_task, _connect_started_at  # noqa: PLW0603
    task = asyncio.create_task(_connect_shared_client())
    _pending_connect_tasks.add(task)
    task.add_done_callback(_on_connect_task_done)
    _connect_task = task
    _connect_started_at = now
    return task


async def _close_temporal_client(client: Client) -> None:
    """Close a discarded Temporal client; ignore SDK/mock close failures."""
    close = getattr(client, "close", None)
    if not callable(close):
        return
    try:
        result = close()
        if asyncio.iscoroutine(result):
            await result
    except Exception:  # noqa: BLE001
        logger.warning("Failed to close discarded Temporal client", exc_info=True)


async def _connect_shared_client() -> Client | None:
    """Open a Temporal client without holding ``_client_lock``.

    Waiters share this task via ``get_shared_client``. Cancellation of a
    waiter must not cancel this connect (see ``asyncio.shield`` there).
    A late success does not replace an already-cached client.
    """
    global _cached_client  # noqa: PLW0603
    try:
        settings = get_settings()
        client = await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
            tls=build_temporal_tls_config(),
            interceptors=[WorkflowAuthClientInterceptor()],
        )
    except (OSError, RuntimeError, RPCError) as e:
        logger.warning("Temporal unavailable for shared client", error=str(e))
        return None

    extra: Client | None = None
    cached: Client | None
    async with _client_lock:
        if _cached_client is None:
            _cached_client = client
            return client
        extra = client if client is not _cached_client else None
        cached = _cached_client

    if extra is not None:
        await _close_temporal_client(extra)
    return cached


async def get_shared_client() -> Client | None:
    """Return a module-level cached Temporal client.

    Connects once and reuses across callers so that API routes,
    lifecycle hooks, and periodic workers share a single gRPC channel.
    The cache is invalidated via :func:`invalidate_client` on
    connection-level errors so the next call reconnects.

    Returns ``None`` (instead of raising) when the Temporal server is
    unreachable, allowing callers to degrade gracefully.

    ``Client.connect`` runs outside ``_client_lock``. The lock only
    serializes starting the in-flight connect task, so a hung connect
    cannot block callers from taking the lock. Waiters use
    ``asyncio.shield`` so a timed-out caller does not cancel an in-flight
    connect. Each waiter is bounded: a timeout returns None to that
    waiter only and leaves the connect running so overlapping waiters can
    still receive it. A new wait replaces ``_connect_task`` when the
    current one is older than the budget, without cancelling waiters
    still joined to the previous task.
    """
    async with _client_lock:
        if _cached_client is not None:
            return _cached_client
        now = time.monotonic()
        connect_task = _start_shared_connect_locked(now) if _should_start_shared_connect(now) else _connect_task
        if connect_task is None:
            connect_task = _start_shared_connect_locked(now)

    try:
        async with asyncio.timeout(CONNECT_TIMEOUT_SECONDS):
            return await asyncio.shield(connect_task)
    except TimeoutError:
        settings = get_settings()
        logger.warning(
            "Temporal connect timed out",
            timeout_seconds=CONNECT_TIMEOUT_SECONDS,
            temporal_address=settings.temporal_address,
            temporal_namespace=settings.temporal_namespace,
        )
        return None


def invalidate_client(client: Client | None = None) -> None:
    """Clear the cached Temporal client so the next call reconnects.

    If *client* is given, the cache is cleared only when it still holds
    that exact instance (identity, not equality). A caller whose client
    was never the shared one — an explicit-override connection, an
    injected test client, or a stale client another caller already
    replaced — must not evict the healthy shared connection. Pass no
    argument for an unconditional clear (tests use this as a reset).

    Leaves ``_connect_task`` in place. An in-flight connect must keep a
    strong reference; ``get_shared_client`` starts a new task only after
    the current one is done or older than the waiter budget.
    """
    global _cached_client  # noqa: PLW0603
    if client is None or _cached_client is client:
        _cached_client = None


def invalidate_on_connection_error(exc: BaseException, client: Client | None = None) -> None:
    """Invalidate the cached client if *exc* is a connection-class RPC error.

    *client* should be the instance that raised *exc* so the cache is
    only cleared when that instance is still the cached one; see
    :func:`invalidate_client` for why identity matters.
    """
    if isinstance(exc, RPCError) and exc.status in CONNECTION_ERRORS:
        invalidate_client(client)
