"""Safe, bounded HTTP execution for the standalone executor image."""
# ruff: noqa: EM101, EM102, TRY003

from __future__ import annotations

import base64
import ipaddress
import json
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

import httpx

_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})
_BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".svc", ".cluster.local")
_MAX_URL_LENGTH = 8_192
_MAX_HEADERS = 100
_MAX_REQUEST_BODY_BYTES = 1_048_576


class CommandError(ValueError):
    """A safe error that can be returned to the stdin caller."""

    def __init__(self, error_type: str, message: str, *, status_code: int | None = None) -> None:
        """Create an error that exposes only a safe, fixed message."""
        super().__init__(message)
        self.error_type = error_type
        self.status_code = status_code

    @classmethod
    def validation(cls, message: str) -> CommandError:
        """Create a validation error."""
        return cls("ValidationError", message)

    @classmethod
    def ssrf(cls, message: str) -> CommandError:
        """Create an SSRF-protection error."""
        return cls("SSRFValidationError", message)


def _response_too_large() -> CommandError:
    return CommandError("ResponseTooLarge", "response exceeds the configured size limit")


@dataclass(frozen=True)
class HttpCommand:
    """Validated input for one HTTP request."""

    method: str
    url: str
    headers: dict[str, str]
    query_params: dict[str, str | int | float | bool | None]
    body: dict[str, Any] | list[Any] | str | None
    timeout_seconds: float


def _validate_public_destination(url: str) -> None:
    """Reject non-public destinations before asking httpx to connect."""
    parsed = urlsplit(url)
    hostname = parsed.hostname
    if not hostname:
        raise CommandError.validation("url must include a hostname")
    normalized_host = hostname.rstrip(".").lower()
    if normalized_host == "localhost" or normalized_host.endswith(_BLOCKED_HOST_SUFFIXES):
        raise CommandError.ssrf("url targets a disallowed hostname")
    try:
        addresses = socket.getaddrinfo(hostname, parsed.port or 443, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise CommandError("DNSResolutionError", "url hostname could not be resolved") from exc

    for address_info in addresses:
        address = ipaddress.ip_address(address_info[4][0])
        if not address.is_global:
            raise CommandError.ssrf("url resolves to a non-public address")


def _string_mapping(value: object, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise CommandError.validation(f"{field_name} must be an object")
    if len(value) > _MAX_HEADERS:
        raise CommandError.validation(f"{field_name} cannot contain more than {_MAX_HEADERS} entries")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise CommandError.validation(f"{field_name} keys and values must be strings")
        result[key] = item
    return result


def _query_mapping(value: object) -> dict[str, str | int | float | bool | None]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise CommandError.validation("query_params must be an object")
    result: dict[str, str | int | float | bool | None] = {}
    for key, item in value.items():
        if not isinstance(key, str) or isinstance(item, (dict, list)):
            raise CommandError.validation("query_params must contain scalar values")
        if item is not None and not isinstance(item, (str, int, float, bool)):
            raise CommandError.validation("query_params must contain scalar values")
        result[key] = item
    return result


def _apply_authentication(headers: dict[str, str], value: object) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        raise CommandError.validation("authentication must be an object")
    auth_type = value.get("type")
    credentials = value.get("credentials")
    if not isinstance(auth_type, str) or not isinstance(credentials, str) or not credentials:
        raise CommandError.validation("authentication requires non-empty type and credentials strings")
    if auth_type in {"bearer", "oauth2"}:
        headers["Authorization"] = f"Bearer {credentials}"
    elif auth_type == "basic":
        encoded = base64.b64encode(credentials.encode()).decode("ascii")
        headers["Authorization"] = f"Basic {encoded}"
    elif auth_type == "api_key":
        headers["X-API-Key"] = credentials
    else:
        raise CommandError.validation("authentication type must be basic, bearer, api_key, or oauth2")


def parse_command(value: object, *, max_timeout_seconds: float) -> HttpCommand:
    """Validate an untrusted JSON command without logging any input values."""
    if not isinstance(value, Mapping):
        raise CommandError.validation("command must be a JSON object")
    method = value.get("method")
    url = value.get("url")
    if not isinstance(method, str) or method.upper() not in _ALLOWED_METHODS:
        raise CommandError.validation("method must be GET, POST, PUT, PATCH, or DELETE")
    if not isinstance(url, str) or not url or len(url) > _MAX_URL_LENGTH:
        raise CommandError.validation("url must be a non-empty HTTP or HTTPS URL")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise CommandError.validation("url must be an HTTP or HTTPS URL without userinfo")
    try:
        _ = parsed.port
    except ValueError as exc:
        raise CommandError.validation("url contains an invalid port") from exc

    timeout = value.get("timeout_seconds", 30)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= max_timeout_seconds:
        raise CommandError.validation(f"timeout_seconds must be between 0 and {max_timeout_seconds:g}")
    headers = _string_mapping(value.get("headers"), "headers")
    _apply_authentication(headers, value.get("authentication"))
    query_params = _query_mapping(value.get("query_params"))
    body = value.get("body")
    if body is not None and not isinstance(body, (dict, list, str)):
        raise CommandError.validation("body must be an object, array, string, or null")
    encoded_body = body if isinstance(body, str) else ""
    if body is not None and not isinstance(body, str):
        encoded_body = json.dumps(body, separators=(",", ":"))
    if len(encoded_body.encode()) > _MAX_REQUEST_BODY_BYTES:
        raise CommandError.validation("body exceeds the 1 MiB limit")
    _validate_public_destination(url)
    return HttpCommand(method.upper(), url, headers, query_params, body, float(timeout))


async def execute_command(
    command: HttpCommand,
    *,
    max_response_bytes: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, Any]:
    """Execute one validated command and return a JSON-serializable result."""
    started = monotonic()
    try:
        async with (
            httpx.AsyncClient(follow_redirects=False, trust_env=False, transport=transport) as client,
            client.stream(
                command.method,
                command.url,
                headers=command.headers,
                params=command.query_params,
                json=command.body if isinstance(command.body, (dict, list)) else None,
                content=command.body if isinstance(command.body, str) else None,
                timeout=command.timeout_seconds,
            ) as response,
        ):
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > max_response_bytes:
                    raise _response_too_large()
                chunks.append(chunk)
    except CommandError:
        raise
    except httpx.TimeoutException as exc:
        raise CommandError("TimeoutError", "HTTP request timed out") from exc
    except httpx.HTTPError as exc:
        raise CommandError(type(exc).__name__, "HTTP request failed") from exc

    content = b"".join(chunks)
    try:
        body: Any = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        body = content.decode(response.encoding or "utf-8", errors="replace")
    elapsed = monotonic() - started
    result: dict[str, Any] = {
        "ok": response.is_success,
        "status_code": response.status_code,
        "headers": dict(response.headers),
        "body": body,
        "elapsed": elapsed,
    }
    if not response.is_success:
        result["error_type"] = "HTTPError"
        result["message"] = f"HTTP {response.status_code} {response.reason_phrase}"
    return result
