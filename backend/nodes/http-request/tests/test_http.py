"""HTTP compatibility and error classification."""

from unittest.mock import patch

import httpx
import pytest
import respx
from syntara_node_http_request import Node
from syntara_node_runtime.runtime import Invocation, execute


def run(inputs, credentials=None):
    with patch("syntara_node_http_request.executor.validate_url_no_ssrf"):
        return execute(
            Node(), Invocation(inputs=inputs, credentials={"resolved": credentials or {}}), lambda _frame: None
        )


@respx.mock
def test_query_json_and_bearer():
    route = respx.post("https://example.com/path?keep=yes&new=value").mock(
        return_value=httpx.Response(200, json={"hello": "world"})
    )
    frame = run(
        {
            "method": "POST",
            "url": "https://example.com/path?keep=yes",
            "query_params": {"new": "value"},
            "body": {"a": 1},
        },
        {"extra_vars": {"auth_type": "bearer", "bearer_token": "top-secret"}},
    )
    assert route.calls[0].request.headers["Authorization"] == "Bearer top-secret"
    assert frame["result"]["Result"]["body"] == {"hello": "world"}
    assert "elapsed" in frame["result"]["Result"]


@pytest.mark.parametrize(
    ("status", "retryable"),
    [(400, False), (401, False), (429, True), (500, False), (502, True), (503, True), (504, True)],
)
@respx.mock
def test_errors(status, retryable):
    respx.get("https://example.com").mock(return_value=httpx.Response(status, text="error"))
    frame = run({"method": "GET", "url": "https://example.com"})
    assert frame["error"] == {"type": "HTTPError", "retryable": retryable}
    assert frame["result"]["Result"]["status_code"] == status


@respx.mock
def test_secret_url_and_redirect():
    respx.get("https://example.com/secret").mock(
        return_value=httpx.Response(302, headers={"location": "https://other.example/"})
    )
    frame = run({"method": "GET"}, {"extra_vars": {"auth_type": "url", "secret_url": "https://example.com/secret"}})
    assert frame["result"]["StatusCode"] == 0
    assert frame["result"]["Result"]["status_code"] == 302


def test_ssrf_is_non_retryable():
    with patch("syntara_node_http_request.executor.validate_url_no_ssrf", side_effect=ValueError("Blocked")):
        frame = execute(
            Node(), Invocation(inputs={"method": "GET", "url": "http://169.254.169.254"}), lambda _frame: None
        )
    assert frame["error"] == {"type": "SSRFValidationError", "retryable": False}


@respx.mock
def test_response_size_limit():
    respx.get("https://example.com").mock(return_value=httpx.Response(200, text="x" * 100))
    with patch("syntara_node_http_request.executor.validate_url_no_ssrf"):
        frame = execute(
            Node(),
            Invocation(inputs={"method": "GET", "url": "https://example.com"}, max_output_bytes=32),
            lambda _: None,
        )
    assert frame["error"]["type"] == "OutputLimitError"


def test_cloud_metadata_is_blocked_even_when_allowed():
    from syntara_node_runtime.runtime import NodeSettings

    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("169.254.169.254", 80))]):
        frame = execute(
            Node(),
            Invocation(
                inputs={"method": "GET", "url": "http://metadata.example"},
                settings=NodeSettings(workflow_http_request_allowed_hosts=["metadata.example"]),
            ),
            lambda _: None,
        )
    assert frame["error"]["type"] == "SSRFValidationError"
