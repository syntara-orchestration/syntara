"""Tests for global request body size middleware."""

import json
from collections.abc import MutableMapping
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from syntara.core.config.base import get_settings
from syntara.core.middleware.request_body_size import RequestBodySizeMiddleware


async def _ok_handler(request: Request) -> JSONResponse:
    body = await request.body()
    return JSONResponse({"bytes": len(body)})


def _build_app() -> RequestBodySizeMiddleware:
    app = Starlette(routes=[Route("/api/v1/test", _ok_handler, methods=["POST", "GET"])])
    return RequestBodySizeMiddleware(app)


@pytest.mark.asyncio
async def test_rejects_content_length_above_limit() -> None:
    middleware = _build_app()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [
            (b"content-length", b"20000000"),
            (b"content-type", b"application/json"),
        ],
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    messages: list[MutableMapping[str, Any]] = []

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    await middleware(scope, receive, send)

    start = messages[0]
    assert start["type"] == "http.response.start"
    assert start["status"] == 413
    body = messages[1]["body"]
    assert isinstance(body, bytes)
    payload = json.loads(body.decode())
    assert payload["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.asyncio
async def test_rejects_streaming_body_above_limit() -> None:
    """Reject when streamed chunks exceed the limit without Content-Length."""

    async def drain_app(scope: Scope, receive: Receive, send: Send) -> None:
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestBodySizeMiddleware(drain_app)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [
            (b"content-type", b"application/json"),
        ],
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    chunks = [b"x" * 5_000_000, b"x" * 5_000_000, b"x" * 5_000_000]
    chunk_iter = iter(chunks)
    messages: list[MutableMapping[str, Any]] = []

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)

    async def receive() -> dict[str, object]:
        try:
            chunk = next(chunk_iter)
            return {"type": "http.request", "body": chunk, "more_body": True}
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}

    await middleware(scope, receive, send)

    start = messages[0]
    assert start["type"] == "http.response.start"
    assert start["status"] == 413
    body = messages[1]["body"]
    assert isinstance(body, bytes)
    payload = json.loads(body.decode())
    assert payload["code"] == "PAYLOAD_TOO_LARGE"


@pytest.mark.asyncio
async def test_allows_small_body() -> None:
    middleware = _build_app()
    payload = b'{"hello":"world"}'
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [
            (b"content-length", str(len(payload)).encode()),
            (b"content-type", b"application/json"),
        ],
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    messages: list[MutableMapping[str, Any]] = []

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": payload, "more_body": False}

    await middleware(scope, receive, send)

    start = messages[0]
    assert start["type"] == "http.response.start"
    assert start["status"] == 200


@pytest.mark.asyncio
async def test_does_not_send_413_after_response_started() -> None:
    """Skip 413 when the downstream app already sent http.response.start."""

    async def early_response_app(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break

    middleware = RequestBodySizeMiddleware(early_response_app)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [
            (b"content-type", b"application/json"),
        ],
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    chunks = [b"x" * 5_000_000, b"x" * 5_000_000, b"x" * 5_000_000]
    chunk_iter = iter(chunks)
    messages: list[MutableMapping[str, Any]] = []

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)

    async def receive() -> dict[str, object]:
        try:
            chunk = next(chunk_iter)
            return {"type": "http.request", "body": chunk, "more_body": True}
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}

    await middleware(scope, receive, send)

    starts = [m for m in messages if m["type"] == "http.response.start"]
    assert len(starts) == 1
    assert starts[0]["status"] == 200


@pytest.mark.asyncio
async def test_skips_get_requests() -> None:
    middleware = _build_app()
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/test",
        "headers": [],
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    messages: list[MutableMapping[str, Any]] = []

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    await middleware(scope, receive, send)

    assert messages[0]["status"] == 200


@pytest.mark.asyncio
async def test_skips_excluded_paths() -> None:
    """Excluded paths bypass the size check even with an oversized Content-Length."""

    async def always_ok_app(scope: Scope, receive: Receive, send: Send) -> None:
        del scope
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    middleware = RequestBodySizeMiddleware(always_ok_app)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/healthz/live",
        "headers": [
            (b"content-length", b"999999999"),
            (b"content-type", b"application/json"),
        ],
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    messages: list[MutableMapping[str, Any]] = []

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    await middleware(scope, receive, send)

    assert messages[0]["status"] == 200


@pytest.mark.asyncio
async def test_rejects_malformed_content_length() -> None:
    middleware = _build_app()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [
            (b"content-length", b"abc"),
            (b"content-type", b"application/json"),
        ],
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    messages: list[MutableMapping[str, Any]] = []

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    await middleware(scope, receive, send)

    start = messages[0]
    assert start["status"] == 400
    payload = json.loads(messages[1]["body"].decode())
    assert payload["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_rejects_negative_content_length() -> None:
    middleware = _build_app()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [
            (b"content-length", b"-1"),
            (b"content-type", b"application/json"),
        ],
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    messages: list[MutableMapping[str, Any]] = []

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    await middleware(scope, receive, send)

    start = messages[0]
    assert start["status"] == 400
    payload = json.loads(messages[1]["body"].decode())
    assert payload["code"] == "BAD_REQUEST"


@pytest.mark.asyncio
async def test_allows_multipart_body_under_computed_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """Multipart bodies use the higher file-upload-derived limit."""
    settings = get_settings()
    monkeypatch.setattr(settings, "file_upload_max_size_mb", 1)
    monkeypatch.setattr(settings, "file_upload_max_files", 1)
    max_bytes = (settings.file_upload_max_size_mb * settings.file_upload_max_files + 1) * 1024 * 1024
    middleware = _build_app()
    payload_size = max_bytes - 1
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [
            (b"content-length", str(payload_size).encode()),
            (b"content-type", b"multipart/form-data; boundary=x"),
        ],
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    messages: list[MutableMapping[str, Any]] = []

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"x" * payload_size, "more_body": False}

    await middleware(scope, receive, send)

    assert messages[0]["status"] == 200


@pytest.mark.asyncio
async def test_rejects_multipart_body_over_computed_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "file_upload_max_size_mb", 1)
    monkeypatch.setattr(settings, "file_upload_max_files", 1)
    max_bytes = (settings.file_upload_max_size_mb * settings.file_upload_max_files + 1) * 1024 * 1024
    middleware = _build_app()
    payload_size = max_bytes + 1
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [
            (b"content-length", str(payload_size).encode()),
            (b"content-type", b"multipart/form-data; boundary=x"),
        ],
        "query_string": b"",
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    messages: list[MutableMapping[str, Any]] = []

    async def send(message: MutableMapping[str, Any]) -> None:
        messages.append(message)

    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": b"", "more_body": False}

    await middleware(scope, receive, send)

    start = messages[0]
    assert start["status"] == 413
    payload = json.loads(messages[1]["body"].decode())
    assert payload["code"] == "PAYLOAD_TOO_LARGE"
