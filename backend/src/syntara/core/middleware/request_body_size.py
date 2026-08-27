"""ASGI middleware enforcing a global HTTP request body size limit.

Rejects oversized bodies before downstream handlers parse JSON or buffer
multipart uploads. Multipart requests use a higher limit derived from file
upload settings. Health, metrics, and documentation paths are excluded.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog

from syntara.api.constants import EXCLUDED_PATH_PREFIXES, EXCLUDED_PATHS
from syntara.core.config.base import get_settings
from syntara.core.error_handlers import PROBLEM_TYPES

if TYPE_CHECKING:
    from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = structlog.stdlib.get_logger(__name__)

_CONTENT_TYPE_HEADER = b"content-type"
_CONTENT_LENGTH_HEADER = b"content-length"
_PROBLEM_JSON = b"application/problem+json"
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH"})


class _BodyTooLargeError(Exception):
    """Internal signal that the streaming body exceeded the configured limit."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


def _header_value(headers: list[tuple[bytes, bytes]], name: bytes) -> str | None:
    """Return the first header value for name (case-insensitive)."""
    for key, value in headers:
        if key.lower() == name:
            return value.decode("latin-1")
    return None


def _is_multipart(content_type: str | None) -> bool:
    if content_type is None:
        return False
    return content_type.lower().startswith("multipart/")


def _max_body_bytes_for_request(content_type: str | None) -> int:
    settings = get_settings()
    if _is_multipart(content_type):
        # One MB headroom for form field metadata beyond raw file bytes.
        return (settings.file_upload_max_size_mb * settings.file_upload_max_files + 1) * 1024 * 1024
    return settings.api_max_request_body_mb * 1024 * 1024


async def _send_413(send: Send, detail: str) -> None:
    """Send a 413 Payload Too Large response with RFC 9457 body."""
    body = {
        "type": PROBLEM_TYPES["payload_too_large"],
        "title": "Payload Too Large",
        "detail": detail,
        "code": "PAYLOAD_TOO_LARGE",
        "retryable": False,
    }
    body_bytes = json.dumps(body).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", _PROBLEM_JSON),
                (b"content-length", str(len(body_bytes)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body_bytes})


def _should_skip_request(scope: Scope) -> bool:
    path: str = scope["path"]
    if path in EXCLUDED_PATHS or path.startswith(EXCLUDED_PATH_PREFIXES):
        return True
    return scope.get("method", "GET") not in _BODY_METHODS


async def _reject_from_content_length(
    scope: Scope,
    send: Send,
    content_length_raw: str,
    max_bytes: int,
) -> bool:
    """Return True when Content-Length exceeds max_bytes and a 413 was sent."""
    try:
        content_length = int(content_length_raw)
    except ValueError:
        await _send_413(send, "Invalid Content-Length header")
        return True

    if content_length > max_bytes:
        detail = f"Request body size {content_length} bytes exceeds maximum of {max_bytes} bytes"
        logger.warning(
            "request_body_too_large",
            path=scope["path"],
            content_length=content_length,
            max_bytes=max_bytes,
        )
        await _send_413(send, detail)
        return True
    return False


class _ResponseStartGuard:
    """Track whether http.response.start has already been sent."""

    def __init__(self, send: Send) -> None:
        self._send = send
        self.started = False

    async def __call__(self, message: Message) -> None:
        if message["type"] == "http.response.start":
            self.started = True
        await self._send(message)


class _LimitedBodyReceiver:
    """Wrap receive() and reject bodies that exceed max_bytes."""

    def __init__(self, receive: Receive, max_bytes: int, path: str) -> None:
        self._receive = receive
        self._max_bytes = max_bytes
        self._path = path
        self._body_complete = False
        self._received_bytes = 0

    async def __call__(self) -> Message:
        if self._body_complete:
            return {"type": "http.request", "body": b"", "more_body": False}

        message = await self._receive()
        if message["type"] != "http.request":
            return message

        self._received_bytes += len(message.get("body", b""))
        if self._received_bytes > self._max_bytes:
            detail = f"Request body exceeds maximum of {self._max_bytes} bytes"
            logger.warning(
                "request_body_too_large",
                path=self._path,
                received_bytes=self._received_bytes,
                max_bytes=self._max_bytes,
            )
            raise _BodyTooLargeError(detail)

        if not message.get("more_body", False):
            self._body_complete = True
        return message


class RequestBodySizeMiddleware:
    """Reject HTTP request bodies that exceed configured size limits."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap the next ASGI application in the body-size limiter."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process an HTTP request, rejecting oversized bodies when configured."""
        if scope["type"] != "http" or _should_skip_request(scope):
            await self.app(scope, receive, send)
            return

        headers = list(scope.get("headers", []))
        content_type = _header_value(headers, _CONTENT_TYPE_HEADER)
        max_bytes = _max_body_bytes_for_request(content_type)
        guard = _ResponseStartGuard(send)

        content_length_raw = _header_value(headers, _CONTENT_LENGTH_HEADER)
        if content_length_raw is not None and await _reject_from_content_length(
            scope, guard, content_length_raw, max_bytes
        ):
            return

        limited_receive = _LimitedBodyReceiver(receive, max_bytes, scope["path"])
        try:
            await self.app(scope, limited_receive, guard)
        except _BodyTooLargeError as exc:
            if not guard.started:
                await _send_413(guard, exc.detail)
