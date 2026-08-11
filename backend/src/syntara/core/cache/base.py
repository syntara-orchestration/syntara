"""Base async Redis client with shared connection lifecycle.

All Redis client classes in Nexus should inherit from
:class:`BaseRedisClient` to share connection setup, teardown, and
context-manager support.  Subclasses set :attr:`_client_name` for
differentiated log messages and implement domain-specific operations.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any, Self

import redis.asyncio as redis
import structlog
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError

from syntara.core.config.base import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from types import TracebackType

logger = structlog.stdlib.get_logger(__name__)


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
