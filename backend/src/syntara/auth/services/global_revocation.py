"""Global token revocation utilities.

Provides helpers that check whether a token was issued before the
system-wide revocation timestamp stored in the
``global_revocation_timestamp`` database table.

Uses an in-process TTLCache to avoid a DB query on every
authenticated request.

**Cache-staleness compensation:**
The revocation check compares the token's ``iat`` against
``revocation_ts + _CACHE_TTL``.  This shifts the rejection boundary
forward by the cache TTL so that even if another node is still serving
a stale cached value, tokens issued during that staleness window are
still rejected.  The trade-off is that tokens issued in the few seconds
*after* a revocation event may require re-authentication — an
acceptable cost for closing the multi-node bypass window.

**Thundering-herd protection:**
An ``asyncio.Lock`` ensures that on cache miss only one coroutine
queries the database; concurrent callers wait for the result.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import structlog
from cachetools import TTLCache
from sqlmodel import select

from syntara.auth.models.global_revocation_timestamp import GlobalRevocationTimestamp

if TYPE_CHECKING:
    from sqlmodel.ext.asyncio.session import AsyncSession

logger = structlog.stdlib.get_logger(__name__)

_CACHE_TTL = 10

_SENTINEL = object()
_revocation_ts_cache: TTLCache[str, datetime | None | object] = TTLCache(maxsize=1, ttl=_CACHE_TTL)
_CACHE_KEY = "global_revocation_ts"
_fetch_lock = asyncio.Lock()


def clear_global_revocation_cache() -> None:
    """Drop the cached revocation timestamp so the next call hits the DB."""
    _revocation_ts_cache.clear()


async def get_global_revocation_timestamp(db: AsyncSession) -> datetime | None:
    """Return the global revocation timestamp, or ``None`` if unset.

    The value is read from the ``global_revocation_timestamp`` singleton
    table.  Returns ``None`` when no row exists or ``revoked_before``
    is ``NULL``.

    Results are cached for ``_CACHE_TTL`` seconds.  An asyncio lock
    ensures only one coroutine fetches from the database on a cache miss.

    Args:
        db: Active database session (reused from the request).

    """
    cached = _revocation_ts_cache.get(_CACHE_KEY, _SENTINEL)
    if cached is not _SENTINEL:
        return cached  # type: ignore[return-value]

    async with _fetch_lock:
        cached = _revocation_ts_cache.get(_CACHE_KEY, _SENTINEL)
        if cached is not _SENTINEL:
            return cached  # type: ignore[return-value]

        result = await db.exec(select(GlobalRevocationTimestamp))
        row = result.one_or_none()

        value = None if (row is None or row.revoked_before is None) else row.revoked_before
        _revocation_ts_cache[_CACHE_KEY] = value
        return value


async def is_token_globally_revoked(iat: datetime | None, db: AsyncSession) -> datetime | None:
    """Check if *iat* falls within the revocation window.

    Tokens issued before ``revocation_ts + _CACHE_TTL`` are rejected.
    The TTL offset compensates for cache staleness across nodes so that
    a revoked token cannot slip through while another node's cache is
    still serving the pre-revocation value.

    Args:
        iat: The token's ``iat`` (issued-at) claim as a datetime.
        db: Active database session (reused from the request).

    Returns:
        The revocation timestamp when the token should be rejected;
        ``None`` otherwise (including when no revocation timestamp is
        configured or *iat* is ``None``).

    """
    if iat is None:
        return None
    revocation_ts = await get_global_revocation_timestamp(db)
    if revocation_ts is None:
        return None
    # Ensure both are tz-aware for comparison
    if iat.tzinfo is None:
        iat = iat.replace(tzinfo=UTC)
    if revocation_ts.tzinfo is None:
        revocation_ts = revocation_ts.replace(tzinfo=UTC)
    if iat < revocation_ts + timedelta(seconds=_CACHE_TTL):
        return revocation_ts
    return None
