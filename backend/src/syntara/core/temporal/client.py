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
import ssl

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
            _cached_client = await Client.connect(
                settings.temporal_address,
                namespace=settings.temporal_namespace,
                tls=build_temporal_tls_config(),
                interceptors=[WorkflowAuthClientInterceptor()],
            )
            return _cached_client
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
