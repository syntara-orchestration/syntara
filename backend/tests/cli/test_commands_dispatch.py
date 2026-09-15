"""Tests for HTTP dispatch helpers in orchestrator_cli.commands.

Covers _create_client, _call_with_rate_limit_retry, and _format_response
using only dataclass stubs for responses — no real HTTP calls are made.
"""

from __future__ import annotations

import dataclasses
import json
import time
from unittest.mock import MagicMock, patch

import pytest
import typer
from orchestrator_cli.commands import (
    _call_with_rate_limit_retry,
    _create_client,
    _format_response,
)

# ---------------------------------------------------------------------------
# Response stubs
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _StatusCode:
    value: int


@dataclasses.dataclass
class _MockResponse:
    status_code: _StatusCode
    is_success: bool
    content: bytes = b""
    headers: dict[str, str] = dataclasses.field(default_factory=dict)
    parsed: object = None


def _ok(content: bytes = b"") -> _MockResponse:
    return _MockResponse(status_code=_StatusCode(200), is_success=True, content=content)


def _error(status: int, content: bytes = b"") -> _MockResponse:
    return _MockResponse(status_code=_StatusCode(status), is_success=False, content=content)


def _rate_limited(retry_after: int = 0) -> _MockResponse:
    return _MockResponse(
        status_code=_StatusCode(429),
        is_success=False,
        headers={"retry-after": str(retry_after)},
    )


# ---------------------------------------------------------------------------
# _create_client
# ---------------------------------------------------------------------------


def test_create_client_raises_and_emits_error_when_no_token(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """_create_client must echo an error and raise Exit(1) when auth is required but token is absent."""
    with pytest.raises(typer.Exit):
        _create_client("http://localhost:8000", None, needs_auth=True)
    assert "APP_CLI_TOKEN" in capsys.readouterr().err


def test_create_client_returns_authenticated_client_when_token_provided() -> None:
    """_create_client returns an AuthenticatedClient when a bearer token is given."""
    mock_mod = MagicMock()
    with patch("orchestrator_cli.commands.importlib.import_module", return_value=mock_mod):
        client = _create_client("http://localhost:8000", "my-token", needs_auth=True)
    mock_mod.AuthenticatedClient.assert_called_once()
    assert client is mock_mod.AuthenticatedClient.return_value


def test_create_client_returns_unauthenticated_client_when_auth_not_required() -> None:
    """_create_client uses the anonymous Client class when needs_auth=False."""
    mock_mod = MagicMock()
    with patch("orchestrator_cli.commands.importlib.import_module", return_value=mock_mod):
        client = _create_client("http://localhost:8000", None, needs_auth=False)
    mock_mod.Client.assert_called_once()
    assert client is mock_mod.Client.return_value


def test_create_client_appends_api_v1_to_base_url() -> None:
    """The client receives base_url + '/api/v1', not the raw base_url."""
    mock_mod = MagicMock()
    with patch("orchestrator_cli.commands.importlib.import_module", return_value=mock_mod):
        _create_client("http://localhost:8000", "tok", needs_auth=True)
    call_kwargs = mock_mod.AuthenticatedClient.call_args[1]
    assert call_kwargs["base_url"].endswith("/api/v1")


# ---------------------------------------------------------------------------
# _call_with_rate_limit_retry
# ---------------------------------------------------------------------------


def test_rate_limit_retry_returns_successful_response() -> None:
    """A 200 response is returned immediately without retrying."""
    ep_mod = MagicMock()
    ep_mod.sync_detailed.return_value = _ok(b'{"id": 1}')

    resp = _call_with_rate_limit_retry(ep_mod, MagicMock(), {})

    assert resp.status_code.value == 200
    assert ep_mod.sync_detailed.call_count == 1


def test_rate_limit_retry_raises_exit_on_4xx(capsys: pytest.CaptureFixture[str]) -> None:
    """A 4xx error must echo status and body to stderr then raise Exit(1)."""
    ep_mod = MagicMock()
    ep_mod.sync_detailed.return_value = _error(404, b'{"detail": "not found"}')

    with pytest.raises(typer.Exit):
        _call_with_rate_limit_retry(ep_mod, MagicMock(), {})
    err = capsys.readouterr().err
    assert "404" in err


def test_rate_limit_retry_raises_exit_on_5xx(capsys: pytest.CaptureFixture[str]) -> None:
    """A 5xx server error must echo to stderr and raise Exit(1)."""
    ep_mod = MagicMock()
    ep_mod.sync_detailed.return_value = _error(500, b'{"detail": "internal error"}')

    with pytest.raises(typer.Exit):
        _call_with_rate_limit_retry(ep_mod, MagicMock(), {})
    err = capsys.readouterr().err
    assert "500" in err


def test_rate_limit_retry_retries_on_429_then_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A single 429 triggers a retry; the second call succeeds and the response is returned."""
    monkeypatch.setattr(time, "sleep", lambda _: None)

    ep_mod = MagicMock()
    ep_mod.sync_detailed.side_effect = [
        _rate_limited(retry_after=0),
        _ok(b'{"ok": true}'),
    ]

    resp = _call_with_rate_limit_retry(ep_mod, MagicMock(), {})

    assert resp.status_code.value == 200
    assert ep_mod.sync_detailed.call_count == 2
    assert "Rate limited" in capsys.readouterr().err


def test_rate_limit_retry_raises_exit_after_max_retries(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Exit(1) is raised after _MAX_RATE_LIMIT_RETRIES consecutive 429 responses."""
    monkeypatch.setattr(time, "sleep", lambda _: None)

    ep_mod = MagicMock()
    ep_mod.sync_detailed.return_value = _rate_limited(retry_after=0)

    with pytest.raises(typer.Exit):
        _call_with_rate_limit_retry(ep_mod, MagicMock(), {})
    assert "maximum retries" in capsys.readouterr().err


def test_rate_limit_retry_parses_non_json_error_body(capsys: pytest.CaptureFixture[str]) -> None:
    """A non-JSON error body is decoded and included in the error output."""
    ep_mod = MagicMock()
    ep_mod.sync_detailed.return_value = _error(502, b"Bad Gateway")

    with pytest.raises(typer.Exit):
        _call_with_rate_limit_retry(ep_mod, MagicMock(), {})
    err = capsys.readouterr().err
    assert "502" in err


# ---------------------------------------------------------------------------
# _format_response
# ---------------------------------------------------------------------------


def test_format_response_prints_parsed_dict_to_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    """When response.parsed has to_dict(), its JSON is pretty-printed to stdout."""
    parsed = MagicMock()
    parsed.to_dict.return_value = {"id": "abc"}
    resp = _MockResponse(status_code=_StatusCode(200), is_success=True, parsed=parsed)

    result = _format_response(resp)

    assert json.loads(capsys.readouterr().out) == {"id": "abc"}
    assert result == {"id": "abc"}


def test_format_response_pretty_prints_json_bytes_when_no_parsed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """JSON bytes in response.content are pretty-printed to stdout when parsed is absent."""
    resp = _ok(b'{"status": "ok"}')

    result = _format_response(resp)

    assert json.loads(capsys.readouterr().out) == {"status": "ok"}
    assert result == {"status": "ok"}


def test_format_response_prints_raw_text_for_non_json_content(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Non-JSON bytes in response.content are decoded and printed as plain text."""
    resp = _ok(b"plain text response")

    _format_response(resp)

    assert "plain text response" in capsys.readouterr().out


def test_format_response_returns_none_when_response_has_no_content(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """An empty response body returns None and produces no stdout output."""
    resp = _ok(b"")

    result = _format_response(resp)

    assert result is None
    assert capsys.readouterr().out == ""
