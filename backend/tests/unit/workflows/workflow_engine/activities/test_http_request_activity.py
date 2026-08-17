"""Tests for execute_http_request_activity and its auth helpers."""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from temporalio.exceptions import ApplicationError

from syntara.workflows.workflow_engine.activities.common import ActivityExecutionError
from syntara.workflows.workflow_engine.activities.http_request_activity import (
    _add_credential_auth_headers,
    execute_http_request_activity,
)


@pytest.fixture(autouse=True)
def _mock_heartbeat() -> Generator[None, None, None]:
    """Auto-mock activity.heartbeat() so tests can run outside a Temporal worker."""
    with patch("temporalio.activity.heartbeat"):
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_response(status_code: int, json_body: object = None, text_body: str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.reason_phrase = {
        200: "OK",
        201: "Created",
        400: "Bad Request",
        404: "Not Found",
        500: "Internal Server Error",
    }.get(status_code, "Unknown")
    resp.headers = {"content-type": "application/json"}
    if json_body is not None:
        resp.json.return_value = json_body
        resp.text = ""
    else:
        resp.json.side_effect = ValueError("not json")
        resp.text = text_body
    return resp


VALID_CONFIG: dict[str, Any] = {"method": "GET", "url": "https://example.com/api"}


def _mock_getaddrinfo(ip: str) -> list[tuple[None, None, None, None, tuple[str, int]]]:
    """Return a mock getaddrinfo result for a given IP."""
    return [(None, None, None, None, (ip, 0))]


# ---------------------------------------------------------------------------
# _add_credential_auth_headers
# ---------------------------------------------------------------------------


class TestAddCredentialAuthHeaders:
    """Tests for _add_credential_auth_headers (Syntara credential system)."""

    def test_bearer_token_sets_authorization(self) -> None:
        headers: dict[str, Any] = {}
        _add_credential_auth_headers(headers, {"auth_type": "bearer", "bearer_token": "tok123"})
        assert headers["Authorization"] == "Bearer tok123"

    def test_bearer_empty_token_raises(self) -> None:
        with pytest.raises(ActivityExecutionError, match="token is empty"):
            _add_credential_auth_headers({}, {"auth_type": "bearer", "bearer_token": ""})

    def test_basic_auth_sets_authorization(self) -> None:
        import base64

        headers: dict[str, Any] = {}
        _add_credential_auth_headers(
            headers, {"auth_type": "basic", "basic_username": "user", "basic_password": "pass"}
        )
        expected = base64.b64encode(b"user:pass").decode("ascii")
        assert headers["Authorization"] == f"Basic {expected}"

    def test_basic_empty_username_raises(self) -> None:
        with pytest.raises(ActivityExecutionError, match="username is empty"):
            _add_credential_auth_headers({}, {"auth_type": "basic", "basic_username": "", "basic_password": "pass"})

    def test_api_key_sets_header(self) -> None:
        headers: dict[str, Any] = {}
        _add_credential_auth_headers(headers, {"auth_type": "api_key", "api_key": "mykey"})
        assert headers["X-API-Key"] == "mykey"

    def test_api_key_falls_back_to_llm_api_key(self) -> None:
        headers: dict[str, Any] = {}
        _add_credential_auth_headers(headers, {"auth_type": "api_key", "api_key": "", "llm_api_key": "llmkey"})
        assert headers["X-API-Key"] == "llmkey"

    def test_api_key_empty_raises(self) -> None:
        with pytest.raises(ActivityExecutionError, match="key is empty"):
            _add_credential_auth_headers({}, {"auth_type": "api_key", "api_key": ""})

    def test_unknown_auth_type_raises(self) -> None:
        with pytest.raises(ActivityExecutionError, match="Unknown credential auth_type"):
            _add_credential_auth_headers({}, {"auth_type": "oauth3"})

    def test_missing_auth_type_logs_warning(self) -> None:
        headers: dict[str, Any] = {}
        _add_credential_auth_headers(headers, {})
        assert "Authorization" not in headers
        assert "X-API-Key" not in headers


# ---------------------------------------------------------------------------
# execute_http_request_activity
# ---------------------------------------------------------------------------


class TestExecuteHttpRequestActivitySuccess:
    """Happy-path tests for execute_http_request_activity."""

    @pytest.mark.asyncio
    async def test_successful_get_json_body(self) -> None:
        resp = _mock_response(200, json_body={"result": "ok"})
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp):
            result = await execute_http_request_activity(VALID_CONFIG, None)
        output = result["output"]
        assert output["status_code"] == 200
        assert output["body"] == {"result": "ok"}
        assert "elapsed" in output

    @pytest.mark.asyncio
    async def test_successful_get_text_body(self) -> None:
        resp = _mock_response(200, text_body="plain text")
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp):
            result = await execute_http_request_activity(VALID_CONFIG, None)
        assert result["output"]["body"] == "plain text"

    @pytest.mark.asyncio
    async def test_post_with_dict_body(self) -> None:
        resp = _mock_response(201, json_body={"id": 1})
        config = {"method": "POST", "url": "https://example.com/api", "body": {"key": "value"}}
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp) as mock_req:
            result = await execute_http_request_activity(config, None)
        assert result["output"]["status_code"] == 201
        call_kwargs = mock_req.call_args.kwargs
        assert call_kwargs["json"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_output_mapping_suppresses_fields(self) -> None:
        resp = _mock_response(200, json_body={"data": "x"})
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp):
            result = await execute_http_request_activity(VALID_CONFIG, {})
        assert result["output"] == {}

    @pytest.mark.asyncio
    async def test_output_mapping_extracts_field(self) -> None:
        resp = _mock_response(200, json_body={"name": "alice"})
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp):
            result = await execute_http_request_activity(VALID_CONFIG, {"username": "${result.body.name}"})
        assert result["output"]["username"] == "alice"

    @pytest.mark.asyncio
    async def test_url_query_params_passed(self) -> None:
        resp = _mock_response(200, json_body={})
        config = {**VALID_CONFIG, "query_params": {"page": "1"}}
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp) as mock_req:
            await execute_http_request_activity(config, None)
        assert mock_req.call_args.kwargs["params"] == {"page": "1"}


class TestExecuteHttpRequestActivityFailures:
    """Error-path tests: config validation, 4xx/5xx, network errors."""

    @pytest.mark.asyncio
    async def test_invalid_config_raises(self) -> None:
        with pytest.raises(ApplicationError) as exc_info:
            await execute_http_request_activity({}, None)  # missing method
        assert exc_info.value.type == "ValidationError"

    @pytest.mark.asyncio
    async def test_404_raises_application_error(self) -> None:
        resp = _mock_response(404)
        with (
            patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_http_request_activity(VALID_CONFIG, None)
        assert exc_info.value.type == "HTTPError"
        assert "404" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_500_raises_application_error(self) -> None:
        resp = _mock_response(500)
        with (
            patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_http_request_activity(VALID_CONFIG, None)
        assert exc_info.value.type == "HTTPError"
        assert "500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_url_query_params_stripped_from_error_message(self) -> None:
        resp = _mock_response(401)
        config = {**VALID_CONFIG, "url": "https://example.com/api?token=secret123"}
        with (
            patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_http_request_activity(config, None)
        assert "secret123" not in str(exc_info.value)
        assert "example.com/api" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_connection_error_raises_application_error(self) -> None:
        import httpx as _httpx

        with (
            patch("httpx.AsyncClient.request", new_callable=AsyncMock, side_effect=_httpx.ConnectError("refused")),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_http_request_activity(VALID_CONFIG, None)
        assert exc_info.value.type == "ConnectError"

    @pytest.mark.asyncio
    async def test_timeout_raises_application_error(self) -> None:
        import httpx as _httpx

        with (
            patch(
                "httpx.AsyncClient.request", new_callable=AsyncMock, side_effect=_httpx.TimeoutException("timed out")
            ),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_http_request_activity(VALID_CONFIG, None)
        assert exc_info.value.non_retryable is True

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [429, 502, 503, 504])
    async def test_transient_http_errors_are_retryable(self, status_code: int) -> None:
        resp = _mock_response(status_code)
        with (
            patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_http_request_activity(VALID_CONFIG, None)
        assert exc_info.value.non_retryable is False, f"HTTP {status_code} should be retryable"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status_code", [400, 401, 403, 404, 422, 500])
    async def test_non_transient_http_errors_are_non_retryable(self, status_code: int) -> None:
        resp = _mock_response(status_code)
        with (
            patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_http_request_activity(VALID_CONFIG, None)
        assert exc_info.value.non_retryable is True, f"HTTP {status_code} should be non-retryable"


class TestExecuteHttpRequestActivityAuth:
    """Tests for credential injection paths in execute_http_request_activity."""

    @pytest.mark.asyncio
    async def test_credential_bearer_injected(self) -> None:
        resp = _mock_response(200, json_body={})

        config = {
            **VALID_CONFIG,
            "_resolved_credentials": {
                "credential_id": "cred-1",
                "extra_vars": {"auth_type": "bearer", "bearer_token": "mytoken"},
            },
        }
        with patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp) as mock_req:
            await execute_http_request_activity(config, None)
        headers_sent = mock_req.call_args.kwargs["headers"]
        assert headers_sent.get("Authorization") == "Bearer mytoken"


_PATCH_GETADDRINFO = "socket.getaddrinfo"


class TestSsrfValidation:
    """Tests for SSRF mitigation in execute_http_request_activity."""

    @pytest.mark.asyncio
    async def test_loopback_rejected(self) -> None:
        """Reject URLs resolving to loopback."""
        config = {"method": "GET", "url": "http://localhost:8181/v1/data"}
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("127.0.0.1")),
            pytest.raises(ApplicationError, match="SSRF blocked"),
        ):
            await execute_http_request_activity(config, None)

    @pytest.mark.asyncio
    async def test_cloud_metadata_rejected(self) -> None:
        """Reject cloud metadata endpoint."""
        config = {"method": "GET", "url": "http://169.254.169.254/latest/meta-data/"}
        with pytest.raises(ApplicationError, match="SSRF blocked"):
            await execute_http_request_activity(config, None)

    @pytest.mark.asyncio
    async def test_public_url_accepted(self) -> None:
        """Accept URLs resolving to public IPs."""
        resp = _mock_response(200, json_body={"ok": True})
        config = {"method": "GET", "url": "https://example.com/api"}
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("93.184.216.34")),
            patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp),
        ):
            result = await execute_http_request_activity(config, None)
        assert result["output"]["status_code"] == 200

    @pytest.mark.asyncio
    async def test_private_ip_rejected(self) -> None:
        """Reject URLs resolving to private IPs."""
        config = {"method": "GET", "url": "https://internal-service.example.com"}
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("10.0.0.1")),
            pytest.raises(ApplicationError, match="SSRF blocked"),
        ):
            await execute_http_request_activity(config, None)


class TestSecretUrlCredential:
    """Tests for Secret URL credential type (auth_type='url')."""

    @pytest.mark.asyncio
    async def test_url_from_credential_overrides_config(self) -> None:
        resp = _mock_response(200, json_body={"ok": True})
        config = {
            **VALID_CONFIG,
            "_resolved_credentials": {
                "credential_id": "cred-url-1",
                "extra_vars": {"auth_type": "url", "secret_url": "https://hooks.slack.com/services/T/B/xxx"},
            },
        }
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("54.1.2.3")),
            patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp) as mock_req,
        ):
            await execute_http_request_activity(config, None)
        assert mock_req.call_args.kwargs["url"] == "https://hooks.slack.com/services/T/B/xxx"

    @pytest.mark.asyncio
    async def test_url_credential_does_not_set_auth_headers(self) -> None:
        resp = _mock_response(200, json_body={})
        config = {
            **VALID_CONFIG,
            "_resolved_credentials": {
                "credential_id": "cred-url-1",
                "extra_vars": {"auth_type": "url", "secret_url": "https://hooks.slack.com/services/T/B/xxx"},
            },
        }
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("54.1.2.3")),
            patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp) as mock_req,
        ):
            await execute_http_request_activity(config, None)
        headers_sent = mock_req.call_args.kwargs["headers"]
        assert "Authorization" not in headers_sent
        assert "X-API-Key" not in headers_sent

    @pytest.mark.asyncio
    async def test_url_credential_empty_raises(self) -> None:
        config = {
            **VALID_CONFIG,
            "_resolved_credentials": {
                "credential_id": "cred-url-1",
                "extra_vars": {"auth_type": "url", "secret_url": ""},
            },
        }
        with pytest.raises(ActivityExecutionError, match="URL is empty"):
            await execute_http_request_activity(config, None)

    @pytest.mark.asyncio
    async def test_url_none_without_credential_raises(self) -> None:
        config = {"method": "GET"}
        with pytest.raises(ApplicationError, match="No URL provided"):
            await execute_http_request_activity(config, None)

    @pytest.mark.asyncio
    async def test_url_credential_redacts_url_in_error(self) -> None:
        resp = _mock_response(401)
        secret_url = "https://hooks.slack.com/services/T/B/supersecret"  # noqa: S105
        config = {
            **VALID_CONFIG,
            "_resolved_credentials": {
                "credential_id": "cred-url-1",
                "extra_vars": {"auth_type": "url", "secret_url": secret_url},
            },
        }
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("54.1.2.3")),
            patch("httpx.AsyncClient.request", new_callable=AsyncMock, return_value=resp),
            pytest.raises(ApplicationError) as exc_info,
        ):
            await execute_http_request_activity(config, None)
        assert "supersecret" not in str(exc_info.value)
        assert "[REDACTED]" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_url_credential_ssrf_private_ip_rejected(self) -> None:
        config = {
            **VALID_CONFIG,
            "_resolved_credentials": {
                "credential_id": "cred-url-1",
                "extra_vars": {"auth_type": "url", "secret_url": "https://internal.example.com/webhook"},
            },
        }
        with (
            patch(_PATCH_GETADDRINFO, return_value=_mock_getaddrinfo("10.0.0.1")),
            pytest.raises(ApplicationError, match="SSRF blocked"),
        ):
            await execute_http_request_activity(config, None)

    @pytest.mark.asyncio
    async def test_url_credential_schemeless_rejected(self) -> None:
        config = {
            **VALID_CONFIG,
            "_resolved_credentials": {
                "credential_id": "cred-url-1",
                "extra_vars": {"auth_type": "url", "secret_url": "//evil.com/hook"},
            },
        }
        with pytest.raises(ActivityExecutionError, match="http:// or https://"):
            await execute_http_request_activity(config, None)
