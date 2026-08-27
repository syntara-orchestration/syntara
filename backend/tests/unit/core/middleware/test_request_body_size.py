"""Tests for global request body size middleware."""

import json
from collections.abc import MutableMapping
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

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
