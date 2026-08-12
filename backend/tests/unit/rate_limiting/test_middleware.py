"""Unit tests for the rate limiting middleware."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from syntara.audit.emitter import AuditActorContext, actor_context_var
from syntara.rate_limiting.middleware import RateLimitMiddleware
from syntara.rate_limiting.token_bucket import TokenBucketResult

if TYPE_CHECKING:
    from collections.abc import MutableMapping

    from starlette.types import Receive, Scope, Send


def _make_scope(
    path: str = "/api/v1/workflows",
    method: str = "GET",
    scope_type: str = "http",
    client: tuple[str, int] | None = ("127.0.0.1", 12345),
) -> dict[str, Any]:
    """Build an ASGI scope dict for testing."""
    scope: dict[str, Any] = {
        "type": scope_type,
        "path": path,
        "method": method,
        "headers": [],
    }
    if client is not None:
        scope["client"] = client
    return scope


async def _ok_app(scope: Scope, receive: Receive, send: Send) -> None:
    """Minimal ASGI app that returns 200 OK."""
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b"ok"})


@pytest.fixture
def mock_token_bucket() -> AsyncMock:
    """Mock token bucket that allows requests by default."""
    bucket = AsyncMock()
    bucket.consume.return_value = TokenBucketResult(allowed=True, remaining=9, limit=10, reset_at=1060.0)
    return bucket


@pytest.fixture
def mock_settings_cache() -> AsyncMock:
    """Mock settings cache with rate limiting enabled."""
    cache = AsyncMock()

    async def get_int_side_effect(key: str) -> int | None:
        if key == "rate_limiting.requests_per_window":
            return 10
        if key == "rate_limiting.window_duration_seconds":
            return 60
        return None

    cache.get_int.side_effect = get_int_side_effect
    return cache


@pytest.fixture
def mock_app_state(
    mock_token_bucket: AsyncMock,
) -> MagicMock:
    """Mock FastAPI application state with rate limit components."""
    state = MagicMock()
    state.rate_limit_token_bucket = mock_token_bucket
    state.settings_cache = None
    return state


@pytest.fixture
def mock_fastapi_app(mock_app_state: MagicMock) -> MagicMock:
    """Mock FastAPI application with state."""
    app = MagicMock()
    app.state = mock_app_state
    return app


@pytest.fixture
def middleware(mock_fastapi_app: MagicMock) -> RateLimitMiddleware:
    """Rate limit middleware instance wired to mock app."""
    return RateLimitMiddleware(_ok_app, fastapi_app=mock_fastapi_app)


class TestRateLimitMiddleware:
    """Tests for RateLimitMiddleware."""

    @pytest.mark.asyncio
    async def test_pass_through_non_http(self, middleware: RateLimitMiddleware) -> None:
        scope = _make_scope(scope_type="websocket")
        send = AsyncMock()

        await middleware(scope, AsyncMock(), send)

        send.assert_awaited()

    @pytest.mark.asyncio
    async def test_pass_through_excluded_path(self, middleware: RateLimitMiddleware) -> None:
        scope = _make_scope(path="/health")
        send = AsyncMock()

        await middleware(scope, AsyncMock(), send)

        # Should pass through without rate limit check
        assert send.await_count >= 1

    @pytest.mark.asyncio
    async def test_pass_through_when_unconfigured(
        self,
        mock_fastapi_app: MagicMock,
    ) -> None:
        mock_fastapi_app.state.rate_limit_token_bucket = None
        mw = RateLimitMiddleware(_ok_app, fastapi_app=mock_fastapi_app)
        scope = _make_scope()
        send = AsyncMock()

        await mw(scope, AsyncMock(), send)

        assert send.await_count >= 1

    @pytest.mark.asyncio
    async def test_unauthenticated_rate_limited_by_ip(
        self,
        middleware: RateLimitMiddleware,
        mock_token_bucket: AsyncMock,
        mock_settings_cache: AsyncMock,
    ) -> None:
        scope = _make_scope(client=("10.0.0.1", 9999))
        messages: list[MutableMapping[str, Any]] = []

        async def capture_send(message: MutableMapping[str, Any]) -> None:
            messages.append(message)

        token = actor_context_var.set(None)
        try:
            with patch(
                "syntara.rate_limiting.middleware.get_runtime_settings",
                return_value=mock_settings_cache,
            ):
                await middleware(scope, AsyncMock(), capture_send)
        finally:
            actor_context_var.reset(token)

        mock_token_bucket.consume.assert_awaited_once_with(
            user_id="ip:10.0.0.1",
            max_tokens=10,
            window_seconds=60,
        )
        start_msg = next(m for m in messages if m["type"] == "http.response.start")
        header_names = {h[0] for h in start_msg["headers"]}
        assert b"x-ratelimit-limit" in header_names

    @pytest.mark.asyncio
    async def test_allowed_request_has_headers(
        self,
        middleware: RateLimitMiddleware,
        mock_token_bucket: AsyncMock,
        mock_settings_cache: AsyncMock,
    ) -> None:
        scope = _make_scope()
        messages: list[MutableMapping[str, Any]] = []

        async def capture_send(message: MutableMapping[str, Any]) -> None:
            messages.append(message)

        actor = AuditActorContext(actor_id=uuid4(), actor_username="user1")
        token = actor_context_var.set(actor)
        try:
            with patch(
                "syntara.rate_limiting.middleware.get_runtime_settings",
                return_value=mock_settings_cache,
            ):
                await middleware(scope, AsyncMock(), capture_send)
        finally:
            actor_context_var.reset(token)

        start_msg = next(m for m in messages if m["type"] == "http.response.start")
        header_names = {h[0] for h in start_msg["headers"]}
        assert b"x-ratelimit-limit" in header_names
        assert b"x-ratelimit-remaining" in header_names
        assert b"x-ratelimit-reset" in header_names

    @pytest.mark.asyncio
    async def test_denied_request_returns_429(
        self,
        middleware: RateLimitMiddleware,
        mock_token_bucket: AsyncMock,
        mock_settings_cache: AsyncMock,
    ) -> None:
        mock_token_bucket.consume.return_value = TokenBucketResult(
            allowed=False, remaining=0, limit=10, reset_at=1060.0, retry_after=5.0
        )
        scope = _make_scope()
        messages: list[MutableMapping[str, Any]] = []

        async def capture_send(message: MutableMapping[str, Any]) -> None:
            messages.append(message)

        actor = AuditActorContext(actor_id=uuid4(), actor_username="user1")
        token = actor_context_var.set(actor)
        try:
            with patch(
                "syntara.rate_limiting.middleware.get_runtime_settings",
                return_value=mock_settings_cache,
            ):
                await middleware(scope, AsyncMock(), capture_send)
        finally:
            actor_context_var.reset(token)

        start_msg = next(m for m in messages if m["type"] == "http.response.start")
        assert start_msg["status"] == 429

        header_dict = {h[0]: h[1] for h in start_msg["headers"]}
        assert b"retry-after" in header_dict
        assert header_dict[b"content-type"] == b"application/problem+json"

        body_msg = next(m for m in messages if m["type"] == "http.response.body")
        body = json.loads(body_msg["body"])
        assert body["code"] == "RATE_LIMITED"
        assert body["retryable"] is True

    @pytest.mark.asyncio
    async def test_redis_failure_allows_request(
        self,
        middleware: RateLimitMiddleware,
        mock_token_bucket: AsyncMock,
        mock_settings_cache: AsyncMock,
    ) -> None:
        mock_token_bucket.consume.side_effect = RedisConnectionError("down")
        scope = _make_scope()
        messages: list[MutableMapping[str, Any]] = []

        async def capture_send(message: MutableMapping[str, Any]) -> None:
            messages.append(message)

        actor = AuditActorContext(actor_id=uuid4(), actor_username="user1")
        token = actor_context_var.set(actor)
        try:
            with patch(
                "syntara.rate_limiting.middleware.get_runtime_settings",
                return_value=mock_settings_cache,
            ):
                await middleware(scope, AsyncMock(), capture_send)
        finally:
            actor_context_var.reset(token)

        start_msg = next(m for m in messages if m["type"] == "http.response.start")
        assert start_msg["status"] == 200

    @pytest.mark.asyncio
    async def test_rate_limit_disabled_passes_through(
        self,
        middleware: RateLimitMiddleware,
    ) -> None:
        """When settings return 0 for requests_per_window, no rate limiting."""
        disabled_cache = AsyncMock()
        disabled_cache.get_int.return_value = 0

        scope = _make_scope()
        send = AsyncMock()
        actor = AuditActorContext(actor_id=uuid4(), actor_username="user1")
        token = actor_context_var.set(actor)
        try:
            with patch(
                "syntara.rate_limiting.middleware.get_runtime_settings",
                return_value=disabled_cache,
            ):
                await middleware(scope, AsyncMock(), send)
        finally:
            actor_context_var.reset(token)

        assert send.await_count >= 1
