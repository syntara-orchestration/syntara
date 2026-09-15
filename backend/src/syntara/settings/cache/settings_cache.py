"""Runtime settings reader with two-tier caching and change notification.

Provides an async interface for reading runtime settings from the database
with TTL-based caching at two levels:

- **L1** — in-process ``dict`` (zero-latency, per-process).
- **L2** — Redis per-key cache (shared across processes, optional).

Settings with ``requires_restart=True`` are cached for the lifetime of
the process.  Other settings expire after their ``cache_ttl_seconds``
(or the default TTL) and are re-fetched on the next :meth:`get` call.

Change notification uses Redis Pub/Sub when available.  A publisher
(in :class:`~syntara.settings.services.settings_service.SettingsService`)
sends the changed key on the ``syntara:settings:changes`` channel after
every successful update.  The subscriber task in this module invalidates
the local cache and re-fetches the authoritative value from the database
before delivering the change to registered :meth:`on_change` callbacks.

When Redis is unavailable the system degrades gracefully:

- L2 is skipped (L1 + DB only).
- A :class:`~syntara.core.workers.periodic.PeriodicWorker` polls for
  changes instead of Pub/Sub.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from syntara.settings.exceptions import SettingTypeError, SettingValidationError
from syntara.settings.store import SettingsStore

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlmodel.ext.asyncio.session import AsyncSession

    from syntara.core.cache.settings_client import SettingsRedisClient

logger = structlog.stdlib.get_logger(__name__)

_runtime_settings: SettingsCache | None = None
_SENTINEL = object()

_DEFAULT_TTL_SECONDS = 60.0


REDIS_KEY_PREFIX = "syntara:settings:"
REDIS_CHANNEL = "syntara:settings:changes"

_signing_key: bytes | None = None


def _derive_signing_key() -> bytes:
    """Derive a purpose-specific HMAC key from the application secret.

    Uses HKDF (RFC 5869) with a unique info parameter to ensure domain
    separation from other HMAC uses (e.g. OIDC state signing).
    """
    global _signing_key  # noqa: PLW0603
    if _signing_key is None:
        from syntara.core.config.base import get_encryption_key  # noqa: PLC0415

        secret = get_encryption_key().get_secret_value()
        hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"settings-pubsub-hmac")
        _signing_key = hkdf.derive(secret.encode())
    return _signing_key


def _compute_hmac(payload: str) -> str:
    """Compute HMAC-SHA256 over a canonical JSON payload."""
    return hmac.new(_derive_signing_key(), payload.encode(), hashlib.sha256).hexdigest()


def _verify_hmac(payload: str, expected_mac: str) -> bool:
    """Verify an HMAC-SHA256 signature using constant-time comparison."""
    actual = _compute_hmac(payload)
    return hmac.compare_digest(actual, expected_mac)


@dataclass
class CachedValue:
    """A single cached setting value with its fetch timestamp."""

    value: Any
    fetched_at: float  # time.monotonic() when fetched from DB
    ttl_seconds: float  # float("inf") for requires_restart=True settings

    def is_fresh(self) -> bool:
        """Return True if the cached value has not expired."""
        if self.ttl_seconds == float("inf"):
            return True
        return (time.monotonic() - self.fetched_at) < self.ttl_seconds


class SettingsCache:
    """Async reader for runtime settings with two-tier caching.

    Values are cached in-process (L1) and optionally in Redis (L2)
    with TTL-based expiry.  Settings marked ``requires_restart=True``
    in the catalog are cached for the lifetime of the process
    (infinite TTL, L1 only).

    Args:
        session_factory: Async session factory — an ``async_sessionmaker`` or
            any callable returning an async context manager that yields an
            :class:`~sqlmodel.ext.asyncio.session.AsyncSession`.
        default_ttl_seconds: Fallback TTL when the catalog entry has no
            ``cache_ttl_seconds`` override.
        redis_enabled: When ``True`` (default), the cache will attempt to
            connect to Redis during :meth:`start_watching` for L2 cache and
            Pub/Sub.  The Redis client lifecycle is managed internally.

    """

    def __init__(
        self,
        *,
        session_factory: Any,  # noqa: ANN401
        default_ttl_seconds: float = _DEFAULT_TTL_SECONDS,
        redis_enabled: bool = True,
    ) -> None:
        """Initialise with an async session factory and optional Redis."""
        self._session_factory = session_factory
        self._default_ttl_seconds = default_ttl_seconds
        self._redis_enabled = redis_enabled
        self._redis_client: SettingsRedisClient | None = None

        # L1 in-memory cache: key -> CachedValue
        self._cache: dict[str, CachedValue] = {}

        # Change callbacks: key -> list of callables
        self._watchers: dict[str, list[Callable[[str, Any], Any]]] = {}

        # Last-known values for watched keys (separate from _cache so
        # that invalidate() doesn't break change detection).
        self._watch_values: dict[str, Any] = {}

        # Polling worker (created lazily in start_watching)
        self._poll_worker: Any = None  # PeriodicWorker, imported lazily

        # Pub/Sub listener task
        self._pubsub_task: asyncio.Task[None] | None = None
        self._pubsub: Any = None  # redis.client.PubSub

        # Async startup task (created by start_watching)
        self._startup_task: asyncio.Task[None] | None = None

        # Track whether Redis was ever reachable (log warning only once)
        self._redis_warned: bool = False

        # Lazily-built catalog lookup dict (instance-scoped for test safety)
        self._catalog_by_key: dict[str, Any] | None = None

    # ------------------------------------------------------------------
    # Catalog lookup
    # ------------------------------------------------------------------

    def _get_catalog_by_key(self) -> dict[str, Any]:
        """Return a dict mapping setting keys to their catalog definitions.

        Lazily built on first access to avoid circular imports.
        Instance-scoped so tests that patch ``SETTINGS_CATALOG`` get a
        fresh lookup without needing to reset module-level state.
        """
        if self._catalog_by_key is None:
            from syntara.settings.catalog import SETTINGS_CATALOG  # noqa: PLC0415

            self._catalog_by_key = {d.key: d for d in SETTINGS_CATALOG}
        return self._catalog_by_key

    # ------------------------------------------------------------------
    # Redis L2 helpers
    # ------------------------------------------------------------------

    def _log_redis_warning(self, event: str, exc: BaseException, **ctx: object) -> None:
        """Log a Redis warning once per outage period.

        Duplicates are suppressed until the flag is reset by a successful
        Redis reconnection in ``_start_pubsub`` or ``_try_acquire_redis_client``.
        """
        if not self._redis_warned:
            logger.warning(event, **ctx, exc_info=exc)
            self._redis_warned = True

    def _redis_key(self, key: str) -> str:
        """Return the Redis key for a setting key."""
        return f"{REDIS_KEY_PREFIX}{key}"

    async def _redis_get(self, key: str) -> Any | None:  # noqa: ANN401
        """Fetch a value from Redis L2 cache.  Returns None on miss or error."""
        if self._redis_client is None:
            return None
        try:
            raw = await self._redis_client.cache_get(self._redis_key(key))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            self._log_redis_warning("settings.redis_l2_get_error", exc, key=key)
            return None

    async def _redis_set(self, key: str, value: Any, ttl_seconds: float) -> None:  # noqa: ANN401
        """Store a value in Redis L2 cache.  Errors are silently ignored."""
        if self._redis_client is None:
            return
        if ttl_seconds == float("inf"):
            # Don't cache requires_restart settings in Redis (process-local)
            return
        try:
            raw = json.dumps(value)
            await self._redis_client.cache_setex(
                self._redis_key(key),
                int(ttl_seconds),
                raw,
            )
        except Exception as exc:  # noqa: BLE001
            self._log_redis_warning("settings.redis_l2_set_error", exc, key=key)

    async def _redis_delete(self, key: str) -> None:
        """Delete a key from Redis L2 cache.  Errors are silently ignored."""
        if self._redis_client is None:
            return
        with contextlib.suppress(Exception):
            await self._redis_client.cache_delete(self._redis_key(key))

    # ------------------------------------------------------------------
    # Read path
    # ------------------------------------------------------------------

    async def get(self, key: str) -> Any:  # noqa: ANN401
        """Return the effective value for a setting key.

        Checks L1 (in-memory) first, then L2 (Redis), then the database.
        On a cache miss or TTL expiry the value is fetched from the next
        tier and stored in all higher tiers.

        If the database is unreachable but a stale L1 cached value exists,
        the stale value is returned and a warning is logged.

        Unknown keys (not in the catalog) are rejected immediately and
        returned as ``None`` without touching any cache tier.  This bounds
        the L1 cache to the finite set of catalog keys.

        Args:
            key: Dot-namespaced setting key, e.g.
                ``'context_manager.max_total_tokens'``.

        Returns:
            The resolved value as a native Python type, or ``None`` if both
            ``value`` and ``default_value`` are unset in the database.

        Raises:
            KeyError: If *key* is not registered in the settings catalog.

        """
        # Reject keys not in the catalog — keeps L1 bounded and prevents
        # cache pollution from attacker-influenced key lookups.
        if key not in self._get_catalog_by_key():
            msg = f"Setting key not in catalog: {key!r}"
            raise KeyError(msg)

        # L1 check
        cached = self._cache.get(key)
        if cached is not None and cached.is_fresh():
            return cached.value

        # L2 check (Redis)
        l2_value = await self._redis_get(key)
        if l2_value is not None:
            ttl = self._resolve_ttl(key)
            self._cache[key] = CachedValue(
                value=l2_value,
                fetched_at=time.monotonic(),
                ttl_seconds=ttl,
            )
            return l2_value

        # Database fallback
        try:
            value = await self._fetch_from_db(key)
        except Exception:
            if cached is not None:
                logger.warning("settings.db_unavailable_serving_stale", key=key)
                return cached.value
            raise

        ttl = self._resolve_ttl(key)
        self._cache[key] = CachedValue(
            value=value,
            fetched_at=time.monotonic(),
            ttl_seconds=ttl,
        )

        # Populate L2
        await self._redis_set(key, value, ttl)

        return value

    async def _fetch_from_db(self, key: str) -> Any:  # noqa: ANN401
        """Fetch the effective value for *key* directly from the database."""
        async with self._session_factory() as session:
            session_obj: AsyncSession = session
            store = SettingsStore(session=session_obj)
            setting = await store.get(key)
            if setting is None:
                logger.debug("settings.not_found", key=key)
                return None
            return setting.value if setting.value is not None else setting.default_value

    def _resolve_ttl(self, key: str) -> float:
        """Determine the cache TTL for *key* based on catalog metadata."""
        defn = self._get_catalog_by_key().get(key)
        if defn is None:
            return self._default_ttl_seconds
        if defn.requires_restart:
            return float("inf")
        if defn.cache_ttl_seconds is not None:
            return float(defn.cache_ttl_seconds)
        return self._default_ttl_seconds

    # ------------------------------------------------------------------
    # Type-checked accessors (unchanged public interface)
    # ------------------------------------------------------------------

    async def _get_typed(
        self,
        key: str,
        expected_types: type | tuple[type, ...],
        type_name: str,
        *,
        default: Any = None,  # noqa: ANN401
        reject_bool: bool = False,
    ) -> Any:  # noqa: ANN401
        """Fetch a setting and validate its runtime type and constraints."""
        value = await self.get(key)
        if value is None:
            if default is not None:
                return default
            raise SettingTypeError(key, type_name, "None")
        if reject_bool and isinstance(value, bool):
            raise SettingTypeError(key, type_name, "bool")
        if not isinstance(value, expected_types):
            raise SettingTypeError(key, type_name, type(value).__name__)
        return self._validate_against_catalog(key, value, default)

    def _validate_against_catalog(
        self,
        key: str,
        value: Any,  # noqa: ANN401
        default: Any,  # noqa: ANN401
    ) -> Any:  # noqa: ANN401
        """Validate *value* against the catalog's ``validation_schema``."""
        from syntara.settings.validators import validate_setting_value  # noqa: PLC0415

        defn = self._get_catalog_by_key().get(key)
        if defn is None or defn.validation_schema is None:
            return value

        try:
            validate_setting_value(
                key=key,
                value=value,
                value_type=defn.value_type,
                validation_schema=defn.validation_schema,
            )
        except SettingValidationError:
            from syntara.settings.seeder import _resolve_default  # noqa: PLC0415

            raw_fallback = defn.default_value if defn.default_value is not None else default
            fallback = _resolve_default(raw_fallback)
            logger.warning(
                "settings.validation_failed_on_read",
                key=key,
                invalid_value=value,
                fallback_value=fallback,
            )
            return fallback

        return value

    async def get_int(self, key: str, *, default: int | None = None) -> int:
        """Return the setting value as an ``int``."""
        return await self._get_typed(key, int, "int", default=default, reject_bool=True)  # type: ignore[no-any-return]

    async def get_float(self, key: str, *, default: float | None = None) -> float:
        """Return the setting value as a ``float``."""
        value = await self._get_typed(key, (int, float), "float", default=default, reject_bool=True)
        return float(value)

    async def get_str(self, key: str, *, default: str | None = None) -> str:
        """Return the setting value as a ``str``."""
        return await self._get_typed(key, str, "str", default=default)  # type: ignore[no-any-return]

    async def get_bool(self, key: str, *, default: bool | None = None) -> bool:
        """Return the setting value as a ``bool``."""
        return await self._get_typed(key, bool, "bool", default=default)  # type: ignore[no-any-return]

    async def get_list(self, key: str, *, default: list[Any] | None = None) -> list[Any]:
        """Return the setting value as a ``list``."""
        return await self._get_typed(key, list, "list", default=default)  # type: ignore[no-any-return]

    async def get_dict(self, key: str, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return the setting value as a ``dict``."""
        return await self._get_typed(key, dict, "dict", default=default)  # type: ignore[no-any-return]

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def get_cached(self, key: str) -> Any | None:  # noqa: ANN401
        """Return the L1-cached value for *key*, or ``None`` on miss.

        Synchronous, read-only access to the in-process cache.  Does not
        touch L2 (Redis) or the database.  Intended for use in synchronous
        callbacks (e.g. ``on_change``) where the L1 entry is guaranteed to
        be populated before the callback fires.
        """
        cached = self._cache.get(key)
        if cached is not None:
            return cached.value
        return None

    async def invalidate(self, key: str) -> None:
        """Evict *key* from L1 and L2 caches.

        The next :meth:`get` call for this key will fetch from the database.

        Args:
            key: Dot-namespaced setting key to evict.

        """
        self._cache.pop(key, None)
        await self._redis_delete(key)

    # ------------------------------------------------------------------
    # Change notification
    # ------------------------------------------------------------------

    def on_change(
        self,
        key: str,
        callback: Callable[[str, Any], Any],
    ) -> None:
        """Register a callback invoked when *key*'s value changes.

        Only settings with ``requires_restart=False`` are watchable.
        Callbacks receive ``(key, new_value)`` and may be sync or async.

        Args:
            key: Dot-namespaced setting key to watch.
            callback: Function called with ``(key, new_value)`` on change.

        Raises:
            ValueError: If the setting has ``requires_restart=True``.

        """
        defn = self._get_catalog_by_key().get(key)
        if defn is not None and defn.requires_restart:
            msg = f"Cannot watch requires_restart=True setting: {key}"
            raise ValueError(msg)

        self._watchers.setdefault(key, []).append(callback)

        # Seed the watch-values tracker from the cache so the first poll
        # has a baseline to compare against.  When no cached value exists
        # the key stays absent; the poll loop's .get(key, _SENTINEL) default
        # then skips the first transition so it establishes the baseline
        # without firing callbacks.
        if key not in self._watch_values:
            cached = self._cache.get(key)
            if cached is not None:
                self._watch_values[key] = cached.value

        logger.info("settings.on_change_registered", key=key)

    # ------------------------------------------------------------------
    # Pub/Sub subscriber
    # ------------------------------------------------------------------

    async def _start_pubsub(self) -> bool:
        """Attempt to start the Redis Pub/Sub subscriber.

        Returns True if Pub/Sub was started, False otherwise.
        """
        if self._redis_client is None:
            return False

        try:
            await self._redis_client.ping()
        except Exception:  # noqa: BLE001
            logger.warning("settings.redis_unavailable_for_pubsub", exc_info=True)
            return False

        # Redis is reachable — reset the warning flag so future L2
        # failures are logged again after a recovery period.
        self._redis_warned = False

        try:
            self._pubsub = await self._redis_client.pubsub_subscribe(REDIS_CHANNEL)
        except Exception:  # noqa: BLE001
            logger.warning("settings.pubsub_subscribe_failed", channel=REDIS_CHANNEL, exc_info=True)
            return False

        self._pubsub_task = asyncio.create_task(self._pubsub_listener())
        logger.info("settings.pubsub_started", channel=REDIS_CHANNEL)
        return True

    async def _stop_pubsub(self) -> None:
        """Stop the Pub/Sub subscriber task."""
        if self._pubsub_task is not None:
            if not self._pubsub_task.done():
                self._pubsub_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await self._pubsub_task
            self._pubsub_task = None

        if self._pubsub is not None:
            with contextlib.suppress(Exception):
                await self._pubsub.unsubscribe(REDIS_CHANNEL)
            with contextlib.suppress(Exception):
                await self._pubsub.aclose()
            self._pubsub = None

    async def _try_acquire_redis_client(self) -> None:
        """Attempt to create a Redis client if one is not yet available.

        Called during :meth:`_start_watching_async` and poll cycles when
        Redis was not initially reachable.  On success the client is
        stored and L2 caching + Pub/Sub become available.  On failure
        the attempt is silently skipped — the next poll cycle will retry.
        """
        if not self._redis_enabled:
            return

        from syntara.core.cache.settings_client import SettingsRedisClient  # noqa: PLC0415

        client = SettingsRedisClient()
        try:
            client.connect()
            await client.ping()
            self._redis_client = client
            self._redis_warned = False
            logger.info("settings.redis_client_acquired")
        except Exception:  # noqa: BLE001
            with contextlib.suppress(Exception):
                await client.disconnect()
            if not self._redis_warned:
                logger.warning("settings.redis_still_unavailable")
                self._redis_warned = True

    async def _maybe_reconnect_pubsub(self) -> None:
        """Attempt to restore Pub/Sub if the listener has died.

        Called at the end of each poll cycle.  If no Redis client exists
        (e.g. Redis was unavailable at startup), attempts to acquire one
        first.  Then, if the listener task is not running, cleans up any
        stale state and tries to re-subscribe.  Failures are silently
        ignored — the next poll cycle will try again.
        """
        if self._redis_client is None:
            await self._try_acquire_redis_client()
        if self._redis_client is None:
            return

        # Still running — nothing to do
        if self._pubsub_task is not None and not self._pubsub_task.done():
            return

        # Clean up completed/failed task reference
        self._pubsub_task = None

        logger.info("settings.pubsub_reconnecting")
        try:
            await self._start_pubsub()
        except Exception:  # noqa: BLE001
            logger.warning("settings.pubsub_reconnect_failed", exc_info=True)

    async def _pubsub_listener(self) -> None:
        """Listen for setting change messages on the Pub/Sub channel."""
        try:
            while True:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None:
                    await asyncio.sleep(0.01)
                    continue

                if message["type"] != "message":
                    continue

                try:
                    payload = json.loads(message["data"])
                    key = payload["key"]
                except (json.JSONDecodeError, KeyError, TypeError):
                    logger.warning(
                        "settings.pubsub_bad_message",
                        data=message.get("data"),
                    )
                    continue

                mac = payload.get("mac")
                if mac is None:
                    logger.warning("settings.pubsub_unsigned_message", key=key)
                    continue

                canonical = json.dumps({"key": key})
                if not _verify_hmac(canonical, mac):
                    logger.warning("settings.pubsub_hmac_invalid", key=key)
                    continue

                await self._handle_change_notification(key)

        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            # Pub/Sub died — polling worker is still running as fallback.
            # Clean up stale pubsub so _maybe_reconnect_pubsub can retry.
            logger.warning("settings.pubsub_listener_error", exc_info=True)
            if self._pubsub is not None:
                with contextlib.suppress(Exception):
                    await self._pubsub.unsubscribe(REDIS_CHANNEL)
                with contextlib.suppress(Exception):
                    await self._pubsub.aclose()
                self._pubsub = None

    async def _handle_change_notification(self, key: str) -> None:
        """Process a change notification from Pub/Sub.

        Re-fetches the authoritative value from the database and then
        invalidates stale cache entries.  The pub/sub message is treated
        as a signal only — the DB is the sole source of truth.

        Fetching before invalidating preserves the graceful-degradation
        guarantee: if the DB is unreachable, the existing cached value
        remains available rather than leaving an empty cache.
        """
        try:
            new_value = await self._fetch_from_db(key)
        except Exception:  # noqa: BLE001
            logger.warning("settings.pubsub_refetch_error", key=key, exc_info=True)
            return

        # DB fetch succeeded — now safe to replace the cached entry.
        await self._redis_delete(key)
        ttl = self._resolve_ttl(key)
        self._cache[key] = CachedValue(
            value=new_value,
            fetched_at=time.monotonic(),
            ttl_seconds=ttl,
        )

        # Check if watchers care about this key
        if key not in self._watchers:
            return

        old_value = self._watch_values.get(key, _SENTINEL)
        self._watch_values[key] = new_value

        if old_value is not _SENTINEL and old_value != new_value:
            logger.info("settings.value_changed", key=key)
            await self._fire_callbacks(key, new_value)

    # ------------------------------------------------------------------
    # Watching lifecycle
    # ------------------------------------------------------------------

    def start_watching(self) -> None:
        """Start watching for setting changes.

        Always starts a :class:`~syntara.core.workers.periodic.PeriodicWorker`
        for polling.  Additionally attempts Redis Pub/Sub for near-real-time
        notifications when a Redis client is available.

        Idempotent — calling twice has no effect.

        """
        if (
            self._poll_worker is not None
            or self._pubsub_task is not None
            or (self._startup_task is not None and not self._startup_task.done())
        ):
            return

        # Apply any @watch_setting registrations before starting
        from syntara.settings.watch import _apply_watchers  # noqa: PLC0415

        _apply_watchers(self)

        # Schedule async startup (we're in sync context here).
        # Store reference so the task is not garbage-collected.
        self._startup_task = asyncio.ensure_future(self._start_watching_async())

    async def _start_watching_async(self) -> None:
        """Async companion to start_watching."""
        try:
            # Always start the polling worker
            from syntara.core.workers.periodic import PeriodicWorker  # noqa: PLC0415

            self._poll_worker = PeriodicWorker(
                name="settings-cache-watcher",
                interval_seconds=self._default_ttl_seconds,
                session_factory=self._session_factory,
                callback=self._poll_watched_keys,
                coordinate=False,
            )
            self._poll_worker.start()

            # Acquire Redis client (if enabled and not already connected)
            if self._redis_client is None:
                await self._try_acquire_redis_client()

            # Also try Pub/Sub for near-real-time notifications
            await self._start_pubsub()
        finally:
            self._startup_task = None

    async def stop_watching(self) -> None:
        """Stop the Pub/Sub subscriber, polling worker, and Redis client.  Idempotent."""
        if self._startup_task is not None and not self._startup_task.done():
            self._startup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._startup_task
            self._startup_task = None

        await self._stop_pubsub()

        if self._poll_worker is not None:
            await self._poll_worker.stop()
            self._poll_worker = None

        if self._redis_client is not None:
            with contextlib.suppress(Exception):
                await self._redis_client.disconnect()
            self._redis_client = None

    async def _poll_watched_keys(
        self,
        _session_factory: Any,  # noqa: ANN401
    ) -> None:
        """Poll all watched keys, detect changes, and invoke callbacks."""
        watched_keys = list(self._watchers.keys())
        logger.debug("settings.poll_cycle_start", watched_keys=watched_keys)
        if not watched_keys:
            return

        for key in watched_keys:
            try:
                new_value = await self._fetch_from_db(key)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "settings.poll_fetch_error",
                    key=key,
                    exc_info=True,
                )
                continue

            old_value = self._watch_values.get(key, _SENTINEL)

            # Update both the cache and the watch-values tracker
            ttl = self._resolve_ttl(key)
            self._cache[key] = CachedValue(
                value=new_value,
                fetched_at=time.monotonic(),
                ttl_seconds=ttl,
            )
            self._watch_values[key] = new_value

            # Fire callbacks only if value actually changed
            if old_value is not _SENTINEL and old_value != new_value:
                logger.info("settings.value_changed", key=key)
                await self._fire_callbacks(key, new_value)

        # Attempt to reconnect Pub/Sub if it died
        await self._maybe_reconnect_pubsub()

    async def _fire_callbacks(self, key: str, new_value: Any) -> None:  # noqa: ANN401
        """Invoke all registered callbacks for *key*."""
        logger.debug("settings.fire_callbacks", key=key)
        for cb in self._watchers.get(key, []):
            try:
                result = cb(key, new_value)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001
                logger.warning(
                    "settings.on_change_callback_error",
                    key=key,
                    callback=getattr(cb, "__qualname__", repr(cb)),
                    exc_info=True,
                )

    # ------------------------------------------------------------------
    # Pub/Sub publishing (called by SettingsService)
    # ------------------------------------------------------------------

    async def publish_change(self, key: str) -> None:
        """Publish a setting-changed notification to the Redis Pub/Sub channel.

        Sends the key only — subscribers invalidate their caches and
        re-fetch the authoritative value from the database.  Best-effort;
        errors are logged and swallowed.

        Called by
        :class:`~syntara.settings.services.settings_service.SettingsService`
        after a successful update commit.

        Args:
            key: The setting key that changed.

        """
        if self._redis_client is None:
            return
        try:
            # json.dumps is deterministic within CPython (dict insertion order
            # is preserved). All replicas sharing the same secret_encryption_key
            # will produce and verify identical MACs.
            canonical = json.dumps({"key": key})
            mac = _compute_hmac(canonical)
            payload = json.dumps({"key": key, "mac": mac})
            await self._redis_client.pubsub_publish(REDIS_CHANNEL, payload)
            logger.debug("settings.change_published", key=key)
        except Exception:  # noqa: BLE001
            logger.warning("settings.publish_change_error", key=key, exc_info=True)


def set_runtime_settings(cache: SettingsCache) -> None:
    """Register the process-wide :class:`SettingsCache` singleton."""
    global _runtime_settings  # noqa: PLW0603
    _runtime_settings = cache


def get_runtime_settings() -> SettingsCache:
    """Return the process-wide :class:`SettingsCache` singleton.

    Raises:
        RuntimeError: If :func:`set_runtime_settings` has not been called.

    """
    if _runtime_settings is None:
        msg = "SettingsCache has not been initialised. Call set_runtime_settings() at startup."
        raise RuntimeError(msg)
    return _runtime_settings
