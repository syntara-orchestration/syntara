"""Shared Temporal client with connection caching.

Provides a single cached :class:`temporalio.client.Client` instance for
use across the application.  The client connects once and is reused; call
:func:`invalidate_client` on connection-level errors so the next
:func:`get_shared_client` call reconnects automatically.

Workers are **not** routed through this module because they require a
custom ``DataConverter`` / ``CredentialPayloadCodec`` for payload
encryption.
"""

from __future__ import annotations

import asyncio
import inspect
import ssl
from datetime import timedelta
from typing import Any

import structlog
from temporalio.client import Client, Interceptor, OutboundInterceptor
from temporalio.service import RPCError, RPCStatusCode

from syntara.core.config.base import get_settings
from syntara.core.tls.temporal import build_temporal_tls_config
from syntara.workflows.workflow_engine.client_interceptor import WorkflowAuthClientInterceptor

logger = structlog.stdlib.get_logger(__name__)

CONNECTION_ERRORS: frozenset[RPCStatusCode] = frozenset(
    {RPCStatusCode.UNAVAILABLE, RPCStatusCode.DEADLINE_EXCEEDED},
)

DEFAULT_RPC_TIMEOUT = timedelta(seconds=10)
CONNECT_TIMEOUT_SECONDS = 10


class _TimeoutInterceptor(OutboundInterceptor):
    """Apply a default ``rpc_timeout`` to every Temporal RPC that lacks one."""

    def __init__(self, next_interceptor: OutboundInterceptor, timeout: timedelta) -> None:
        super().__init__(next_interceptor)
        self._timeout = timeout


def _make_timeout_override(name: str) -> Any:  # noqa: ANN401
    async def _override(self: _TimeoutInterceptor, rpc_input: Any, *args: Any, **kwargs: Any) -> Any:  # noqa: ANN401
        if hasattr(rpc_input, "rpc_timeout") and rpc_input.rpc_timeout is None:
            object.__setattr__(rpc_input, "rpc_timeout", self._timeout)
        return await getattr(self.next, name)(rpc_input, *args, **kwargs)

    _override.__name__ = name
    _override.__qualname__ = f"_TimeoutInterceptor.{name}"
    return _override


for _name, _method in inspect.getmembers(OutboundInterceptor, predicate=inspect.iscoroutinefunction):
    if not _name.startswith("_"):
        setattr(_TimeoutInterceptor, _name, _make_timeout_override(_name))


class _TimeoutInterceptorFactory(Interceptor):
    def __init__(self, timeout: timedelta) -> None:
        super().__init__()
        self._timeout = timeout

    def intercept_client(self, next_interceptor: OutboundInterceptor) -> OutboundInterceptor:
        return _TimeoutInterceptor(next_interceptor, self._timeout)


def build_default_interceptors() -> list[Interceptor]:
    """Return the standard interceptor stack for Temporal clients.

    Bundles the RPC timeout interceptor and HMAC auth interceptor so
    callers don't need to import private symbols.
    """
    return [_TimeoutInterceptorFactory(DEFAULT_RPC_TIMEOUT), WorkflowAuthClientInterceptor()]


_client_lock = asyncio.Lock()
_cached_client: Client | None = None


async def get_shared_client() -> Client | None:
    """Return a module-level cached Temporal client.

    Connects once and reuses across callers so that API routes,
    lifecycle hooks, and periodic workers share a single gRPC channel.
    The cache is invalidated via :func:`invalidate_client` on
    connection-level errors so the next call reconnects.

    Returns ``None`` (instead of raising) when the Temporal server is
    unreachable, allowing callers to degrade gracefully.
    """
    global _cached_client  # noqa: PLW0603

    # Fast path: avoid lock acquisition when the client is already cached.
    # Local snapshot so mypy doesn't narrow the global to None after
    # this check, which would make the re-check inside the lock unreachable.
    cached = _cached_client
    if cached is not None:
        return cached

    async with _client_lock:
        # Another coroutine may have connected while we waited for the lock.
        if _cached_client is not None:
            return _cached_client

        try:
            settings = get_settings()
            # Timeout so a hanging gRPC connect can't hold the lock
            # and block all callers (lock convoy → nginx 504s).
            _cached_client = await asyncio.wait_for(
                Client.connect(
                    settings.temporal_address,
                    namespace=settings.temporal_namespace,
                    tls=build_temporal_tls_config(),
                    interceptors=build_default_interceptors(),
                ),
                timeout=CONNECT_TIMEOUT_SECONDS,
            )
            return _cached_client
        except TimeoutError:
            logger.warning("Temporal connect timed out")
        except ssl.SSLError:
            logger.exception("Temporal TLS/auth failure")
        except (OSError, RuntimeError, RPCError) as e:
            logger.warning("Temporal unavailable for shared client", error=str(e))
        except Exception:
            logger.exception("Unexpected error connecting to Temporal")
        return None


def invalidate_client() -> None:
    """Clear the cached Temporal client so the next call reconnects."""
    global _cached_client  # noqa: PLW0603
    _cached_client = None


def invalidate_on_connection_error(exc: BaseException) -> None:
    """Invalidate the cached client if *exc* is a connection-class RPC error."""
    if isinstance(exc, RPCError) and exc.status in CONNECTION_ERRORS:
        invalidate_client()
