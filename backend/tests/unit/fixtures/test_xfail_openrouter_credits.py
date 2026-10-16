"""Unit tests for the OpenRouter-credits xfail plugin's pure logic."""

from __future__ import annotations

import httpx
import pytest
from orchestrator_test_sdk.e2e.openrouter import OPENROUTER_KEY_URL

from tests.fixtures.xfail_openrouter_credits import (
    _credits_exhausted,
    is_openrouter_credit_error,
)


def _client_for(handler: httpx.MockTransport) -> httpx.Client:
    """Return an httpx client that uses *handler* as its transport."""
    return httpx.Client(transport=handler)


def _json_handler(status_code: int, payload: dict[str, object]) -> httpx.MockTransport:
    def _handle(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == OPENROUTER_KEY_URL
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(_handle)


@pytest.mark.parametrize(
    "text",
    [
        "Failed: agent: AgentOrchestratorError: The LLM provider rejected the request due to insufficient credits.",
        "INSUFFICIENT_CREDITS",
        "Error code: 402 - This request requires more credits",
        "HTTP 402: Payment Required",
        "HTTP status 402",
        "status code 402",
        "This request requires more credits, or fewer max_tokens",
        "insufficient credit",
        (
            "{'error': {'message': 'Insufficient credits. Add more using "
            "https://openrouter.ai/settings/credits', 'code': 402, "
            "'metadata': {'limit_source': 'openrouter_credits'}}}"
        ),
        "'limit_source': 'openrouter_credits'",
    ],
    ids=[
        "classified_detail",
        "error_code",
        "error_code_402",
        "http_402",
        "http_status_402",
        "status_code_402",
        "requires_more_credits",
        "insufficient_credit_singular",
        "openrouter_402_body",
        "openrouter_credits_limit_source",
    ],
)
def test_is_openrouter_credit_error_matches(text: str) -> None:
    assert is_openrouter_credit_error(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Failed: agent: AgentOrchestratorError: An unexpected error occurred during LLM streaming. Please try again.",
        "AssertionError: activities['prep'] == 'completed'",
        # Bare 402 must not match — pytest longrepr includes line numbers like file.py:402:
        "backend/tests/e2e/workflows/test_workflow_nodes.py:402: in test_script_then_agentic",
        # UUID hex must not trip a naive "402" substring match
        "llm_model_id = '2c210ebc-8739-4a58-abf6-5eb2ab1e802d'",
        "",
        "rate limit exceeded",
        "HTTP 401: Unauthorized",
        # Marker name in the traceback must not look like the OpenRouter payload field
        "@pytest.mark.xfail_openrouter_credits",
    ],
    ids=[
        "unknown_streaming",
        "script_assert",
        "line_number_402",
        "uuid",
        "empty",
        "rate_limit",
        "auth_401",
        "marker_name",
    ],
)
def test_is_openrouter_credit_error_rejects_unrelated_failures(text: str) -> None:
    assert is_openrouter_credit_error(text) is False


def test_credits_exhausted_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_OPENROUTER_API_KEY", raising=False)
    assert _credits_exhausted() is False


def test_credits_exhausted_on_zero_remaining(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_OPENROUTER_API_KEY", "sk-test")
    with _client_for(_json_handler(200, {"data": {"limit_remaining": 0}})) as client:
        assert _credits_exhausted(client=client) is True


def test_credits_exhausted_on_http_402(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_OPENROUTER_API_KEY", "sk-test")
    with _client_for(_json_handler(402, {"error": "payment required"})) as client:
        assert _credits_exhausted(client=client) is True


def test_credits_not_exhausted_when_remaining_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_OPENROUTER_API_KEY", "sk-test")
    with _client_for(_json_handler(200, {"data": {"limit_remaining": 8.5}})) as client:
        assert _credits_exhausted(client=client) is False


def test_credits_not_exhausted_when_limit_is_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_OPENROUTER_API_KEY", "sk-test")
    with _client_for(_json_handler(200, {"data": {"limit_remaining": None}})) as client:
        assert _credits_exhausted(client=client) is False


def test_credits_not_exhausted_on_network_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_OPENROUTER_API_KEY", "sk-test")

    def _handle(request: httpx.Request) -> httpx.Response:
        msg = "connect"
        raise httpx.ConnectError(msg)

    with _client_for(httpx.MockTransport(_handle)) as client:
        assert _credits_exhausted(client=client) is False


def test_credits_not_exhausted_on_unauthorized_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_OPENROUTER_API_KEY", "sk-test")
    with _client_for(_json_handler(401, {"error": "unauthorized"})) as client:
        assert _credits_exhausted(client=client) is False
