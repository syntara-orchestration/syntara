"""Tests for global request body size middleware."""

import json
from collections.abc import MutableMapping
from typing import Any

import pytest
from fastapi import FastAPI, Form
from pydantic import BaseModel
from starlette.applications import Starlette
from starlette.datastructures import FormData
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import Receive, Scope, Send

from syntara.core.config.base import get_settings
from syntara.core.constants import RequestLimits
from syntara.core.middleware.request_body_size import (
    BodyTooLargeError,
    RequestBodySizeMiddleware,
    body_too_large_exception_handler,
)


async def _ok_handler(request: Request) -> JSONResponse:
    body = await request.body()
    return JSONResponse({"bytes": len(body)})


def _build_app() -> RequestBodySizeMiddleware:
    app = Starlette(routes=[Route("/api/v1/test", _ok_handler, methods=["POST", "GET"])])
    return RequestBodySizeMiddleware(app)


def _build_fastapi_app_with_body_limit() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestBodySizeMiddleware)
    app.add_exception_handler(BodyTooLargeError, body_too_large_exception_handler)  # type: ignore[arg-type]
    return app


async def _assert_oversized_fastapi_returns_413(app: FastAPI, *, content_type: bytes) -> None:
    chunks = [b"x" * 5_000_000, b"x" * 5_000_000, b"x" * 5_000_000]
    chunk_iter = iter(chunks)
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [
            (b"content-type", content_type),
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
        try:
            chunk = next(chunk_iter)
            return {"type": "http.request", "body": chunk, "more_body": True}
        except StopIteration:
            return {"type": "http.request", "body": b"", "more_body": False}

    await app(scope, receive, send)

    start = messages[0]
    assert start["type"] == "http.response.start"
    assert start["status"] == 413
    body = messages[1]["body"]
    assert isinstance(body, bytes)
    payload = json.loads(body.decode())
    assert payload["code"] == "PAYLOAD_TOO_LARGE"


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


@pytest.mark.asyncio
async def test_multipart_limit_clamped_to_hard_ceiling(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with generous file-upload settings, multipart bodies cannot exceed the hard ceiling."""
    settings = get_settings()
    monkeypatch.setattr(settings, "file_upload_max_size_mb", 500)
    monkeypatch.setattr(settings, "file_upload_max_files", 100)
    middleware = _build_app()
    payload_size = RequestLimits.MAX_MULTIPART_BODY_BYTES + 1
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


@pytest.mark.asyncio
async def test_fastapi_typed_json_returns_413_without_content_length() -> None:
    """FastAPI JSON body parsing must surface BodyTooLargeError as 413, not 400."""
    app = _build_fastapi_app_with_body_limit()

    class Payload(BaseModel):
        data: str

    @app.post("/api/v1/test")
    async def post_test(payload: Payload) -> dict[str, str]:
        return {"data": payload.data}

    await _assert_oversized_fastapi_returns_413(app, content_type=b"application/json")


@pytest.mark.asyncio
async def test_fastapi_form_returns_413_without_content_length(monkeypatch: pytest.MonkeyPatch) -> None:
    """FastAPI form body parsing must surface BodyTooLargeError as 413, not 400."""
    original_get_form = Request._get_form

    async def get_form_with_large_parts(
        self,
        *,
        max_files: float = 1000,
        max_fields: float = 1000,
        max_part_size: int = 1024 * 1024,
    ) -> FormData:
        return await original_get_form(
            self,
            max_files=max_files,
            max_fields=max_fields,
            max_part_size=20 * 1024 * 1024,
        )

    monkeypatch.setattr(Request, "_get_form", get_form_with_large_parts)

    app = _build_fastapi_app_with_body_limit()

    @app.post("/api/v1/test")
    async def post_test(name: str = Form(...)) -> dict[str, str]:
        return {"name": name}

    await _assert_oversized_fastapi_returns_413(app, content_type=b"application/x-www-form-urlencoded")
