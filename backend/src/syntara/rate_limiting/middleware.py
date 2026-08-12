"""ASGI middleware for API rate limiting.

Enforces a global per-user token bucket rate limit using Redis.
When unconfigured (default), all requests pass through unrestricted.

Reads ``actor_context_var`` for per-user rate limit keys.  For
mTLS-authenticated requests the audit middleware sets this from the
client certificate; for JWT-authenticated requests the FastAPI auth
dependency sets it after cryptographic verification.  Because auth
dependencies run *inside* the downstream app, the rate limit check
(which runs before the downstream call) sees an empty actor for JWT
requests and falls back to IP-based rate limiting.

Must execute after the audit middleware in the ASGI chain (registered
*before* ``AuditMiddleware`` in ``add_middleware`` calls, since
Starlette inverts the registration order).
"""

from __future__ import annotations

import json
import math
from typing import TYPE_CHECKING

import structlog
from redis.exceptions import RedisError

from syntara.api.constants import EXCLUDED_PATH_PREFIXES, EXCLUDED_PATHS
from syntara.audit.emitter import actor_context_var
from syntara.core.error_handlers import PROBLEM_TYPES
from syntara.rate_limiting.settings import get_rate_limit_config
from syntara.settings.cache.settings_cache import get_runtime_settings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

    from syntara.rate_limiting.token_bucket import TokenBucket, TokenBucketResult

logger = structlog.stdlib.get_logger(__name__)

_RATE_LIMIT_HEADER = b"x-ratelimit-limit"
_RATE_LIMIT_REMAINING_HEADER = b"x-ratelimit-remaining"
_RATE_LIMIT_RESET_HEADER = b"x-ratelimit-reset"
_RETRY_AFTER_HEADER = b"retry-after"
_CONTENT_TYPE_HEADER = b"content-type"
_PROBLEM_JSON = b"application/problem+json"


class RateLimitMiddleware:
    """ASGI middleware that enforces per-user token bucket rate limiting.

    When rate limiting is unconfigured (``requests_per_window == 0``),
    all requests pass through without overhead.  On Redis failure the
    middleware fails open (allows the request).

    Args:
        app: The next ASGI application in the chain.
        fastapi_app: FastAPI instance whose ``state`` carries rate
            limiting components (set during lifespan startup).

    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        fastapi_app: FastAPI,
    ) -> None:
        """Initialise the middleware."""
        self.app = app
        self._fastapi_app = fastapi_app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process an ASGI request, applying rate limiting when configured."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope["path"]
        if path in EXCLUDED_PATHS or path.startswith(EXCLUDED_PATH_PREFIXES):
            await self.app(scope, receive, send)
            return

        result = await self._check_rate_limit(scope)
        if result is None:
            await self.app(scope, receive, send)
            return

        if result.allowed:
            rate_limit_headers = _build_rate_limit_headers(result.limit, result.remaining, result.reset_at)

            async def send_with_headers(message: Message) -> None:
                if message["type"] == "http.response.start":
                    existing: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                    existing.extend(rate_limit_headers)
                    message = {**message, "headers": existing}
                await send(message)

            await self.app(scope, receive, send_with_headers)
        else:
            await _send_429(send, result.limit, result.reset_at, result.retry_after or 1.0)

    async def _check_rate_limit(self, scope: Scope) -> TokenBucketResult | None:
        """Evaluate whether the current request should be rate limited.

        Returns a :class:`TokenBucketResult` when rate limiting applies,
        or ``None`` when the request should pass through unrestricted
        (unconfigured or Redis unavailable).

        Authenticated requests are keyed by actor ID; unauthenticated
        requests fall back to the client IP address so that endpoints
        like ``/auth/login`` are still protected.
        """
        state = self._fastapi_app.state
        token_bucket: TokenBucket | None = getattr(state, "rate_limit_token_bucket", None)
        if token_bucket is None:
            return None

        settings_cache = getattr(state, "settings_cache", None) or get_runtime_settings()
        config = await get_rate_limit_config(settings_cache)
        if config is None:
            return None

        requests_per_window, window_seconds = config

        actor = actor_context_var.get()
        if actor is not None and actor.actor_id is not None:
            rate_limit_key = str(actor.actor_id)
        else:
            client: tuple[str, int] | None = scope.get("client")
            if client is None:
                return None
            rate_limit_key = f"ip:{client[0]}"

        try:
            return await token_bucket.consume(
                user_id=rate_limit_key,
                max_tokens=requests_per_window,
                window_seconds=window_seconds,
            )
        except RedisError:
            logger.warning("rate_limit_redis_unavailable", rate_limit_key=rate_limit_key)
            return None


def _build_rate_limit_headers(limit: int, remaining: int, reset_at: float) -> list[tuple[bytes, bytes]]:
    """Build the ``X-RateLimit-*`` response headers."""
    return [
        (_RATE_LIMIT_HEADER, str(limit).encode()),
        (_RATE_LIMIT_REMAINING_HEADER, str(remaining).encode()),
        (_RATE_LIMIT_RESET_HEADER, str(math.ceil(reset_at)).encode()),
    ]


async def _send_429(
    send: Send,
    limit: int,
    reset_at: float,
    retry_after: float,
) -> None:
    """Send a 429 Too Many Requests response with RFC 9457 body."""
    retry_after_int = math.ceil(retry_after)

    body = {
        "type": PROBLEM_TYPES.get("rate_limited", "https://api.example.com/errors/rate-limited"),
        "title": "Too Many Requests",
        "detail": f"Rate limit exceeded. Try again in {retry_after_int} seconds.",
        "code": "RATE_LIMITED",
        "retryable": True,
    }
    body_bytes = json.dumps(body).encode()

    headers: list[tuple[bytes, bytes]] = [
        (_CONTENT_TYPE_HEADER, _PROBLEM_JSON),
        (_RETRY_AFTER_HEADER, str(retry_after_int).encode()),
        *_build_rate_limit_headers(limit, 0, reset_at),
        (b"content-length", str(len(body_bytes)).encode()),
    ]

    await send(
        {
            "type": "http.response.start",
            "status": 429,
            "headers": headers,
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body_bytes,
        }
    )
