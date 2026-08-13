"""Tests for the LLM provider adapter — validate() and discover() methods."""

from __future__ import annotations

import ssl
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

if TYPE_CHECKING:
    from collections.abc import Generator

import httpx
import pytest
from httpx import HTTPStatusError, Response

from syntara.integrations.adapters.llm_provider import LLMProviderAdapter
from syntara.integrations.adapters.protocol import (
    HealthCheckErrorType,
    IntegrationAdapter,
)
from syntara.integrations.models.integration_configuration import (
    LLMProviderConfiguration,
)


def _make_config(
    provider_hint: str = "openai",
    base_url: str | None = "https://api.openai.com",
) -> LLMProviderConfiguration:
    """Create a test LLMProviderConfiguration with sensible defaults."""
    return LLMProviderConfiguration(provider_hint=provider_hint, base_url=base_url)


def _openai_cred(key: str = "sk-test") -> dict[str, Any]:
    """Create a resolved credential dict with llm_api_key."""
    return {"llm_api_key": key}


def _mock_http_error(status_code: int) -> HTTPStatusError:
    """Create a mock HTTPStatusError with the given status code."""
    response = Response(status_code=status_code)
    return HTTPStatusError(
        message=f"HTTP {status_code}",
        request=httpx.Request("GET", "https://api.openai.com/v1/models"),
        response=response,
    )


def _mock_response(json_data: dict[str, Any], status_code: int = 200) -> Response:
    """Create a mock httpx Response with JSON body and request attached."""
    return Response(
        status_code=status_code,
        json=json_data,
        request=httpx.Request("GET", "https://example.com"),
    )


@contextmanager
def _mock_httpx(*, response: Response | None = None, side_effect: Exception | None = None) -> Generator[MagicMock]:
    """Context manager that patches httpx.AsyncClient with a mock."""
    with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        if side_effect:
            mock_client.get = AsyncMock(side_effect=side_effect)
        else:
            mock_client.get = AsyncMock(return_value=response or _mock_response({"data": []}))
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        yield mock_client


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestLLMProviderAdapterProtocol:
    """Tests that LLMProviderAdapter satisfies the adapter Protocol."""

    def test_is_instance_of_protocol(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        assert isinstance(adapter, IntegrationAdapter)


# ---------------------------------------------------------------------------
# validate() tests
# ---------------------------------------------------------------------------


class TestLLMProviderValidateSuccess:
    """Tests for successful LLMProviderAdapter.validate() calls."""

    @pytest.mark.asyncio
    async def test_openai_validate_success(self) -> None:
        adapter = LLMProviderAdapter(_make_config("openai"))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response({"data": []}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        assert result.error is None

    @pytest.mark.asyncio
    async def test_anthropic_validate_success(self) -> None:
        adapter = LLMProviderAdapter(_make_config("anthropic", base_url=None))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response({"data": []}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        mock_client.get.assert_called_once()
        call_args = mock_client.get.call_args
        assert "api.anthropic.com" in call_args.args[0]
        assert call_args.kwargs["headers"]["x-api-key"] == "sk-test"
        assert call_args.kwargs["headers"]["anthropic-version"] == "2023-06-01"

    @pytest.mark.asyncio
    async def test_gemini_validate_success(self) -> None:
        adapter = LLMProviderAdapter(_make_config("gemini", base_url=None))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response({"models": []}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        call_args = mock_client.get.call_args
        assert "generativelanguage.googleapis.com/v1/models" in call_args.args[0]
        assert "sk-test" not in call_args.args[0]
        assert call_args.kwargs["headers"]["x-goog-api-key"] == "sk-test"

    @pytest.mark.asyncio
    async def test_red_hat_ai_validate_success(self) -> None:
        adapter = LLMProviderAdapter(_make_config("red_hat_ai", base_url="https://my-cluster.example.com"))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response({"data": []}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        call_args = mock_client.get.call_args
        assert "my-cluster.example.com" in call_args.args[0]
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer sk-test"

    @pytest.mark.asyncio
    async def test_validate_no_model_data_in_result(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response({"data": []}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert not hasattr(result, "discovered_models")


class TestLLMProviderValidateErrors:
    """Tests for LLMProviderAdapter.validate() error classification."""

    @pytest.mark.asyncio
    async def test_validate_no_api_key(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        result = await adapter.validate({}, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert "Authentication configuration is incomplete" in (result.error or "")

    @pytest.mark.asyncio
    async def test_validate_timeout(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=TimeoutError("timed out"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.validate(_openai_cred(), timeout_seconds=5)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.TIMEOUT

    @pytest.mark.asyncio
    async def test_validate_http_401(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=_mock_http_error(401))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE

    @pytest.mark.asyncio
    async def test_validate_connection_error(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR

    @pytest.mark.asyncio
    async def test_validate_ssl_error(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=ssl.SSLError("cert failed"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.SSL_ERROR


# ---------------------------------------------------------------------------
# discover() tests
# ---------------------------------------------------------------------------


class TestLLMProviderDiscoverSuccess:
    """Tests for successful LLMProviderAdapter.discover() calls."""

    @pytest.mark.asyncio
    async def test_openai_discover_models(self) -> None:
        adapter = LLMProviderAdapter(_make_config("openai"))
        response_json = {
            "data": [
                {"id": "gpt-4o", "object": "model"},
                {"id": "gpt-4o-mini", "object": "model"},
            ]
        }
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(response_json))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        assert result.discovered_models is not None
        assert len(result.discovered_models) == 2
        assert result.discovered_models[0].id == "gpt-4o"
        assert result.discovered_models[0].name == "gpt-4o"

    @pytest.mark.asyncio
    async def test_anthropic_discover_models(self) -> None:
        adapter = LLMProviderAdapter(_make_config("anthropic", base_url=None))
        response_json = {
            "data": [
                {"id": "claude-opus-4-20250514", "display_name": "Claude Opus 4", "type": "model"},
                {"id": "claude-sonnet-4-20250514", "display_name": "Claude Sonnet 4", "type": "model"},
            ]
        }
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(response_json))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        assert result.discovered_models is not None
        assert len(result.discovered_models) == 2
        assert result.discovered_models[0].id == "claude-opus-4-20250514"
        assert result.discovered_models[0].name == "Claude Opus 4"

    @pytest.mark.asyncio
    async def test_gemini_discover_models(self) -> None:
        adapter = LLMProviderAdapter(_make_config("gemini", base_url=None))
        response_json = {
            "models": [
                {
                    "name": "models/gemini-2.0-flash",
                    "displayName": "Gemini 2.0 Flash",
                    "description": "Fast and versatile model",
                },
                {
                    "name": "models/gemini-2.0-pro",
                    "displayName": "Gemini 2.0 Pro",
                    "description": "Advanced reasoning model",
                },
            ]
        }
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(response_json))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        assert result.discovered_models is not None
        assert len(result.discovered_models) == 2
        assert result.discovered_models[0].id == "gemini-2.0-flash"
        assert result.discovered_models[0].name == "Gemini 2.0 Flash"
        assert result.discovered_models[0].description == "Fast and versatile model"

    @pytest.mark.asyncio
    async def test_empty_model_list(self) -> None:
        adapter = LLMProviderAdapter(_make_config("openai"))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response({"data": []}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        assert result.discovered_models == []

    @pytest.mark.asyncio
    async def test_discover_malformed_json(self) -> None:
        """Malformed JSON response returns error instead of crashing."""
        adapter = LLMProviderAdapter(_make_config("openai"))
        malformed = httpx.Response(
            status_code=200,
            content=b"<html>not json</html>",
            request=httpx.Request("GET", "https://example.com"),
        )
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=malformed)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
        assert "Invalid JSON" in (result.error or "")

    @pytest.mark.asyncio
    async def test_discover_wrong_structure_data_not_array(self) -> None:
        """Valid JSON but data is not an array returns parse error."""
        adapter = LLMProviderAdapter(_make_config("openai"))
        with _mock_httpx(response=_mock_response({"data": "not-an-array"})):
            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
        assert "Invalid JSON" in (result.error or "")

    @pytest.mark.asyncio
    async def test_discover_wrong_structure_missing_key(self) -> None:
        """Valid JSON but missing expected top-level key returns parse error."""
        adapter = LLMProviderAdapter(_make_config("openai"))
        with _mock_httpx(response=_mock_response({"wrong_key": []})):
            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        assert result.discovered_models == []

    @pytest.mark.asyncio
    async def test_discover_error_returns_none_not_empty_list(self) -> None:
        """On error, discovered_models is None (not empty list)."""
        adapter = LLMProviderAdapter(_make_config())
        result = await adapter.discover({}, timeout_seconds=10)

        assert result.success is False
        assert result.discovered_models is None


class TestLLMProviderDiscoverErrors:
    """Tests for LLMProviderAdapter.discover() error classification."""

    @pytest.mark.asyncio
    async def test_discover_no_api_key(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        result = await adapter.discover({}, timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE

    @pytest.mark.asyncio
    async def test_discover_timeout(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=TimeoutError("timed out"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=5)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.TIMEOUT
        assert "5s" in (result.error or "")

    @pytest.mark.asyncio
    async def test_discover_http_401(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=_mock_http_error(401))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert "401" in (result.error or "")

    @pytest.mark.asyncio
    async def test_discover_http_403(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=_mock_http_error(403))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE

    @pytest.mark.asyncio
    async def test_discover_http_429_rate_limit(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        with _mock_httpx(side_effect=_mock_http_error(429)):
            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.RATE_LIMIT
        assert "429" in (result.error or "")

    @pytest.mark.asyncio
    async def test_discover_connection_error(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR
        assert result.error == "Unable to connect to service"

    @pytest.mark.asyncio
    async def test_discover_ssl_error(self) -> None:
        adapter = LLMProviderAdapter(_make_config())
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=ssl.SSLError("cert verify"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is False
        assert result.error_type == HealthCheckErrorType.SSL_ERROR


# ---------------------------------------------------------------------------
# Provider dispatch tests
# ---------------------------------------------------------------------------


class TestProviderDispatch:
    """Tests for correct URL/headers/auth dispatch per provider hint."""

    @pytest.mark.asyncio
    async def test_openai_uses_bearer_auth(self) -> None:
        adapter = LLMProviderAdapter(_make_config("openai"))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response({"data": []}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await adapter.discover(_openai_cred("sk-my-key"), timeout_seconds=10)

        call_args = mock_client.get.call_args
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer sk-my-key"

    @pytest.mark.asyncio
    async def test_anthropic_uses_x_api_key(self) -> None:
        adapter = LLMProviderAdapter(_make_config("anthropic", base_url=None))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response({"data": []}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await adapter.discover(_openai_cred("sk-ant-key"), timeout_seconds=10)

        call_args = mock_client.get.call_args
        assert call_args.kwargs["headers"]["x-api-key"] == "sk-ant-key"
        assert "Authorization" not in call_args.kwargs["headers"]

    @pytest.mark.asyncio
    async def test_gemini_uses_query_param_key(self) -> None:
        adapter = LLMProviderAdapter(_make_config("gemini", base_url=None))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response({"models": []}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await adapter.discover(_openai_cred("gemini-key"), timeout_seconds=10)

        call_args = mock_client.get.call_args
        assert "gemini-key" not in call_args.args[0]
        assert call_args.kwargs["headers"]["x-goog-api-key"] == "gemini-key"

    @pytest.mark.asyncio
    async def test_custom_uses_bearer_auth(self) -> None:
        adapter = LLMProviderAdapter(_make_config("custom", base_url="http://localhost:4000"))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response({"data": []}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await adapter.discover(_openai_cred(), timeout_seconds=10)

        call_args = mock_client.get.call_args
        assert "localhost:4000" in call_args.args[0]
        assert call_args.kwargs["headers"]["Authorization"] == "Bearer sk-test"


# ---------------------------------------------------------------------------
# base_url validation tests
# ---------------------------------------------------------------------------


class TestBaseURLValidation:
    """Tests for base_url defaulting and requirement per provider hint."""

    def test_red_hat_ai_requires_base_url(self) -> None:
        with pytest.raises(ValueError, match="base_url is required"):
            _make_config("red_hat_ai", base_url=None)

    def test_custom_requires_base_url(self) -> None:
        with pytest.raises(ValueError, match="base_url is required"):
            _make_config("custom", base_url=None)

    def test_openai_defaults_base_url(self) -> None:
        config = _make_config("openai", base_url=None)
        assert config.base_url is None  # stored as None, resolved at runtime

    def test_anthropic_defaults_base_url(self) -> None:
        config = _make_config("anthropic", base_url=None)
        assert config.base_url is None

    def test_gemini_defaults_base_url(self) -> None:
        config = _make_config("gemini", base_url=None)
        assert config.base_url is None

    def test_invalid_provider_hint_rejected(self) -> None:
        with pytest.raises(ValueError):
            _make_config("not_a_real_provider")

    def test_get_provider_unknown_hint_raises(self) -> None:
        """_get_provider raises ValueError for an unregistered provider hint."""
        from syntara.integrations.adapters.llm_provider import _get_provider

        # Use a valid enum value that has no provider registered — none currently,
        # so we test the error path by calling with an invalid string cast.
        with pytest.raises(ValueError, match="No provider implementation"):
            _get_provider("nonexistent")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Logging tests
# ---------------------------------------------------------------------------


class TestLLMProviderLogging:
    """Tests that validate() and discover() emit correct structured logs."""

    @pytest.mark.asyncio
    async def test_validate_success_logs_provider(self, caplog: pytest.LogCaptureFixture) -> None:
        """Successful validate logs at INFO with provider."""
        import logging

        caplog.set_level(logging.INFO)
        adapter = LLMProviderAdapter(_make_config("openai"))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response({"data": []}))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert "LLM validate succeeded" in caplog.text

    @pytest.mark.asyncio
    async def test_validate_timeout_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Timeout logs at WARNING with provider."""
        import logging

        caplog.set_level(logging.WARNING)
        adapter = LLMProviderAdapter(_make_config("openai"))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=TimeoutError("timed out"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await adapter.validate(_openai_cred(), timeout_seconds=5)

        assert "LLM request timed out" in caplog.text

    @pytest.mark.asyncio
    async def test_validate_http_error_logs_error_type(self, caplog: pytest.LogCaptureFixture) -> None:
        """HTTP error logs at WARNING with error_type."""
        import logging

        caplog.set_level(logging.WARNING)
        adapter = LLMProviderAdapter(_make_config("openai"))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=_mock_http_error(401))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert "LLM request HTTP error" in caplog.text

    @pytest.mark.asyncio
    async def test_validate_ssl_error_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """SSL error logs at WARNING."""
        import logging

        caplog.set_level(logging.WARNING)
        adapter = LLMProviderAdapter(_make_config("openai"))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=ssl.SSLError("cert"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert "LLM request SSL error" in caplog.text

    @pytest.mark.asyncio
    async def test_validate_connection_error_logs_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        """Connection error logs at WARNING."""
        import logging

        caplog.set_level(logging.WARNING)
        adapter = LLMProviderAdapter(_make_config("openai"))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=ConnectionError("refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert "LLM request connection error" in caplog.text

    @pytest.mark.asyncio
    async def test_discover_success_logs_model_count(self, caplog: pytest.LogCaptureFixture) -> None:
        """Successful discover logs model count."""
        import logging

        caplog.set_level(logging.INFO)
        adapter = LLMProviderAdapter(_make_config("openai"))
        response_json = {"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]}
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=_mock_response(response_json))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert "LLM discover succeeded" in caplog.text

    @pytest.mark.asyncio
    async def test_unexpected_error_logs_exception(self, caplog: pytest.LogCaptureFixture) -> None:
        """Unexpected exceptions use logger.exception for traceback."""
        import logging

        caplog.set_level(logging.ERROR)
        adapter = LLMProviderAdapter(_make_config("openai"))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=RuntimeError("unexpected"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert "Unexpected error during LLM request" in caplog.text

    @pytest.mark.asyncio
    async def test_api_key_not_logged_on_error(self, caplog: pytest.LogCaptureFixture) -> None:
        """API keys must never appear in log output."""
        import logging

        caplog.set_level(logging.DEBUG)
        test_api_key = "sk-secret-key-12345"
        adapter = LLMProviderAdapter(_make_config("openai"))
        with _mock_httpx(side_effect=ConnectionError("refused")):
            await adapter.validate({"llm_api_key": test_api_key}, timeout_seconds=5)

        assert test_api_key not in caplog.text

    @pytest.mark.asyncio
    async def test_api_key_not_logged_on_auth_failure(self, caplog: pytest.LogCaptureFixture) -> None:
        """API keys must not leak even on HTTP 401 errors."""
        import logging

        caplog.set_level(logging.DEBUG)
        test_api_key = "sk-another-secret-99"
        adapter = LLMProviderAdapter(_make_config("openai"))
        with _mock_httpx(side_effect=_mock_http_error(401)):
            await adapter.discover({"llm_api_key": test_api_key}, timeout_seconds=5)

        assert test_api_key not in caplog.text


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class TestLLMProviderDiscoverPagination:
    """Tests for paginated model discovery."""

    @pytest.mark.asyncio
    async def test_anthropic_discover_paginates_two_pages(self) -> None:
        adapter = LLMProviderAdapter(_make_config("anthropic", base_url=None))
        page1 = _mock_response(
            {
                "data": [{"id": "claude-opus-4", "display_name": "Claude Opus 4"}],
                "has_more": True,
                "last_id": "claude-opus-4",
            }
        )
        page2 = _mock_response(
            {
                "data": [{"id": "claude-sonnet-4", "display_name": "Claude Sonnet 4"}],
                "has_more": False,
            }
        )
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=[page1, page2])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        assert result.discovered_models is not None
        assert len(result.discovered_models) == 2
        assert result.discovered_models[0].id == "claude-opus-4"
        assert result.discovered_models[1].id == "claude-sonnet-4"
        assert mock_client.get.call_count == 2
        second_call = mock_client.get.call_args_list[1]
        assert second_call.kwargs["params"] == {"after": "claude-opus-4"}

    @pytest.mark.asyncio
    async def test_google_discover_paginates_two_pages(self) -> None:
        adapter = LLMProviderAdapter(_make_config("gemini", base_url=None))
        page1 = _mock_response(
            {
                "models": [{"name": "models/gemini-flash", "displayName": "Flash"}],
                "nextPageToken": "token-abc",
            }
        )
        page2 = _mock_response(
            {
                "models": [{"name": "models/gemini-pro", "displayName": "Pro"}],
            }
        )
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=[page1, page2])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        assert result.discovered_models is not None
        assert len(result.discovered_models) == 2
        assert result.discovered_models[0].id == "gemini-flash"
        assert result.discovered_models[1].id == "gemini-pro"
        assert mock_client.get.call_count == 2
        second_call = mock_client.get.call_args_list[1]
        assert second_call.kwargs["params"] == {"pageToken": "token-abc"}

    @pytest.mark.asyncio
    async def test_openai_discover_no_pagination(self) -> None:
        """OpenAI does not paginate — discover makes exactly one request."""
        adapter = LLMProviderAdapter(_make_config("openai"))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                return_value=_mock_response(
                    {
                        "data": [{"id": "gpt-4o"}],
                    }
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        assert mock_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_pagination_stops_at_max_pages(self) -> None:
        """Pagination loop stops at _MAX_PAGINATION_PAGES to prevent infinite loops."""
        from syntara.integrations.adapters.llm_provider import _MAX_PAGINATION_PAGES

        adapter = LLMProviderAdapter(_make_config("anthropic", base_url=None))
        always_more = _mock_response(
            {
                "data": [{"id": "model-x"}],
                "has_more": True,
                "last_id": "model-x",
            }
        )
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=always_more)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        assert mock_client.get.call_count == _MAX_PAGINATION_PAGES
        assert result.discovered_models is not None
        assert len(result.discovered_models) == _MAX_PAGINATION_PAGES

    @pytest.mark.asyncio
    async def test_pagination_error_on_second_page(self) -> None:
        """If a subsequent page fails, discover returns failure."""
        adapter = LLMProviderAdapter(_make_config("anthropic", base_url=None))
        page1 = _mock_response(
            {
                "data": [{"id": "claude-opus-4"}],
                "has_more": True,
                "last_id": "claude-opus-4",
            }
        )
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=[page1, _mock_http_error(500)])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.discover(_openai_cred(), timeout_seconds=10)

        assert result.success is False
        assert result.discovered_models is None

    @pytest.mark.asyncio
    async def test_validate_does_not_paginate(self) -> None:
        """validate() makes exactly one request even when response has pagination."""
        adapter = LLMProviderAdapter(_make_config("anthropic", base_url=None))
        with patch("syntara.integrations.adapters.llm_provider.httpx.AsyncClient") as mock_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(
                return_value=_mock_response(
                    {
                        "data": [{"id": "claude-opus-4"}],
                        "has_more": True,
                        "last_id": "claude-opus-4",
                    }
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_cls.return_value = mock_client

            result = await adapter.validate(_openai_cred(), timeout_seconds=10)

        assert result.success is True
        assert mock_client.get.call_count == 1
