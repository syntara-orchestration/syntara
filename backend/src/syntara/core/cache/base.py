"""Base async Redis client with shared connection lifecycle.

All Redis client classes in Nexus should inherit from
:class:`BaseRedisClient` to share connection setup, teardown, and
context-manager support.  Subclasses set :attr:`_client_name` for
differentiated log messages and implement domain-specific operations.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any, Self

import redis.asyncio as redis
import structlog
from redis.exceptions import BusyLoadingError, ConnectionError as RedisConnectionError, ResponseError

from syntara.core.config.base import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from types import TracebackType

logger = structlog.stdlib.get_logger(__name__)

# Pool exhaustion is retryable; use exponential backoff
_POOL_EXHAUSTION_RETRYABLE_ERRORS = (BusyLoadingError,)


@contextlib.asynccontextmanager
async def redis_error_handler(operation: str, **log_context: Any) -> AsyncGenerator[None, None]:  # noqa: ANN401
    """Standardised error handling for Redis operations.

    Catches ``RedisConnectionError``, ``ResponseError`` (logged and
    re-raised) and ``OSError`` (wrapped in ``RedisConnectionError``).

    Args:
        operation: Short label used as the log-event prefix
            (e.g. ``"cache_get"``).
        **log_context: Extra key-value pairs forwarded to the logger.

    """
    try:
        yield
    except (RedisConnectionError, ResponseError):
        logger.exception("redis_operation_error", operation=operation, **log_context)
        raise
    except OSError as e:
        logger.exception("redis_network_error", operation=operation, **log_context)
        msg = f"Network error: {e}"
        raise RedisConnectionError(msg) from e


async def redis_operation_with_backoff(
    operation_fn: Any,  # noqa: ANN401
    operation_name: str,
    max_retries: int = 3,
    initial_backoff_ms: int = 10,
    **log_context: Any,  # noqa: ANN401
) -> Any:  # noqa: ANN401
    """Execute a Redis operation with exponential backoff for transient failures.

    Handles pool exhaustion and other transient errors with exponential backoff.
    Operations like cache writes can safely retry; operations like cache reads
    should only retry for recoverable errors (not "key not found").

    Args:
        operation_fn: Async callable to execute (should raise RedisConnectionError on failure)
        operation_name: Log name for the operation (e.g., "cache_setex")
        max_retries: Maximum number of retries (default: 3)
        initial_backoff_ms: Initial backoff in milliseconds (default: 10)
        **log_context: Extra log context to pass through

    Returns:
        The result of operation_fn() if successful

    Raises:
        RedisConnectionError: If all retries exhausted

    """
    backoff_ms = initial_backoff_ms
    last_error: RedisConnectionError | None = None

    for attempt in range(max_retries + 1):
        try:
            return await operation_fn()
        except RedisConnectionError as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    "redis_operation_retry",
                    operation=operation_name,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    backoff_ms=backoff_ms,
                    **log_context,
                )
                await asyncio.sleep(backoff_ms / 1000.0)
                backoff_ms = min(backoff_ms * 2, 500)  # Cap backoff at 500ms
            else:
                logger.error(
                    "redis_operation_failed_retries_exhausted",
                    operation=operation_name,
                    attempts=max_retries + 1,
                    **log_context,
                )

    if last_error:
        raise last_error
    msg = f"Redis operation '{operation_name}' failed"
    raise RedisConnectionError(msg)


_NOT_CONNECTED_SUFFIX = " client not connected"


class BaseRedisClient:
    """Shared async Redis connection lifecycle.

    Subclasses inherit ``connect``, ``disconnect``, and the async
    context-manager protocol.  Override :attr:`_client_name` with a
    short label (e.g. ``"stream"``, ``"cache"``) used in log messages.

    Recommended usage is as an async context manager::

        async with MyCacheClient() as client:
            await client.some_operation()

    Attributes:
        _client: Underlying async Redis instance (``None`` until connected).
        _settings: Application settings providing host/port/password/etc.

    """

    _client_name: str = "redis"

    def __init__(self) -> None:
        """Initialise connection state and load settings."""
        self._client: redis.Redis | None = None
        self._settings = get_settings()

    # -- context manager -------------------------------------------------

    async def __aenter__(self) -> Self:
        """Enter the async context manager and connect."""
        self.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the async context manager and disconnect."""
        await self.disconnect()

    # -- connection lifecycle --------------------------------------------

    def connect(self) -> None:
        """Create the underlying Redis client (lazy — no I/O until first command).

        Idempotent; calling when already connected is a no-op.

        Raises:
            RedisConnectionError: If client initialisation fails.

        """
        if self._client is not None:
            return
        try:
            self._client = redis.Redis(
                host=self._settings.cache_host,
                port=self._settings.cache_port,
                db=self._settings.cache_db,
                password=(self._settings.cache_password.get_secret_value() if self._settings.cache_password else None),
                decode_responses=True,
                max_connections=self._settings.cache_connection_pool_size,
            )
            logger.info("cache_client_connected", client=self._client_name)
        except RedisConnectionError:
            logger.exception("cache_client_connect_failed", client=self._client_name)
            raise
        except OSError as e:
            logger.exception("cache_client_connect_network_error", client=self._client_name)
            msg = f"Network error: {e}"
            raise RedisConnectionError(msg) from e

    async def disconnect(self) -> None:
        """Close the Redis connection and release pool resources.

        Safe to call multiple times.
        """
        if self._client:
            try:
                await self._client.aclose()
                self._client = None
                logger.info("cache_client_disconnected", client=self._client_name)
            except (RedisConnectionError, OSError, RuntimeError) as e:
                logger.warning("cache_client_disconnect_error", client=self._client_name, error=str(e))
                self._client = None

    def _ensure_connected(self) -> redis.Redis:
        """Return the connected client, calling :meth:`connect` if needed.

        Raises:
            RedisConnectionError: If connect fails or client is still ``None``.

        """
        if self._client is None:
            self.connect()
        if self._client is None:
            msg = self._client_name + _NOT_CONNECTED_SUFFIX
            raise RedisConnectionError(msg)
        return self._client
