"""Tests for the standalone stdin-driven HTTP executor."""

from unittest.mock import patch

import httpx
import pytest

from syntara.http_executor.executor import CommandError, execute_command, parse_command


def _public_address() -> list[tuple[object, object, object, object, tuple[str, int]]]:
    return [(None, None, None, None, ("93.184.216.34", 443))]


def test_parse_command_applies_bearer_auth() -> None:
    with patch("socket.getaddrinfo", return_value=_public_address()):
        command = parse_command(
            {
                "method": "get",
                "url": "https://example.com",
                "authentication": {"type": "bearer", "credentials": "secret"},
            },
            max_timeout_seconds=60,
        )
    assert command.method == "GET"
    assert command.headers["Authorization"] == "Bearer secret"


def test_parse_command_rejects_private_destination() -> None:
    with patch(
        "socket.getaddrinfo",
        return_value=[(None, None, None, None, ("10.0.0.10", 443))],
    ):
        with pytest.raises(CommandError, match="non-public") as error:
            parse_command({"method": "GET", "url": "https://internal.example"}, max_timeout_seconds=60)
    assert error.value.error_type == "SSRFValidationError"


@pytest.mark.asyncio
async def test_execute_command_returns_json_response() -> None:
    with patch("socket.getaddrinfo", return_value=_public_address()):
        command = parse_command(
            {"method": "POST", "url": "https://example.com", "body": {"ok": True}},
            max_timeout_seconds=60,
        )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.content == b'{"ok":true}'
        return httpx.Response(201, json={"id": 1})

    result = await execute_command(command, max_response_bytes=1024, transport=httpx.MockTransport(handler))
    assert result["ok"] is True
    assert result["status_code"] == 201
    assert result["body"] == {"id": 1}


@pytest.mark.asyncio
async def test_execute_command_rejects_response_over_limit() -> None:
    with patch("socket.getaddrinfo", return_value=_public_address()):
        command = parse_command({"method": "GET", "url": "https://example.com"}, max_timeout_seconds=60)
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=b"too large"))
    with pytest.raises(CommandError, match="size limit") as error:
        await execute_command(command, max_response_bytes=1, transport=transport)
    assert error.value.error_type == "ResponseTooLarge"
