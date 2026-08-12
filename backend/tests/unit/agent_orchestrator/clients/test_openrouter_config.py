"""Unit tests for OpenRouter LLM configuration."""

import subprocess
import tempfile
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from syntara.agent_orchestrator.clients.openrouter_config import get_openrouter_llm
from syntara.agent_orchestrator.exceptions import LLMConfigurationError
from syntara.core.config.base import get_settings


@pytest.fixture(scope="module")
def sample_ca_cert() -> str:
    """Generate a valid self-signed CA certificate for testing."""
    with (
        tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as key_f,
        tempfile.NamedTemporaryFile(suffix=".pem", delete=False) as cert_f,
    ):
        subprocess.run(  # noqa: S603
            [  # noqa: S607
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-keyout",
                key_f.name,
                "-out",
                cert_f.name,
                "-days",
                "1",
                "-nodes",
                "-subj",
                "/CN=test-ca",
            ],
            capture_output=True,
            check=True,
        )
        return Path(cert_f.name).read_text()


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Generator[None, None, None]:
    """Clear settings cache before each test to ensure fresh settings."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def mock_runtime_settings_unset() -> Generator[AsyncMock, None, None]:
    """Mock runtime settings where agentic.max_completion_tokens is 0 (no cap)."""
    mock_cache = AsyncMock()
    mock_cache.get_int = AsyncMock(return_value=0)
    with patch(
        "syntara.agent_orchestrator.clients.openrouter_config.get_runtime_settings",
        return_value=mock_cache,
    ):
        yield mock_cache


@pytest.fixture
def mock_runtime_settings_with_cap() -> Generator[AsyncMock, None, None]:
    """Mock runtime settings where agentic.max_completion_tokens is set to 4096."""
    mock_cache = AsyncMock()
    mock_cache.get_int = AsyncMock(return_value=4096)
    with patch(
        "syntara.agent_orchestrator.clients.openrouter_config.get_runtime_settings",
        return_value=mock_cache,
    ):
        yield mock_cache


class TestGetOpenRouterLLM:
    """Tests for get_openrouter_llm function."""

    @pytest.mark.anyio
    async def test_raises_error_when_api_key_missing(self) -> None:
        """Test that missing API key raises LLMConfigurationError."""
        with pytest.raises(LLMConfigurationError, match="No LLM API key available"):
            await get_openrouter_llm()

    @pytest.mark.anyio
    async def test_raises_error_when_api_key_empty(self) -> None:
        """Test that empty API key raises LLMConfigurationError."""
        with pytest.raises(LLMConfigurationError, match="No LLM API key available"):
            await get_openrouter_llm(api_key="")

    @pytest.mark.anyio
    async def test_creates_llm_with_explicit_api_key(self, mock_runtime_settings_unset: AsyncMock) -> None:
        """Test that explicit api_key creates LLM successfully."""
        llm, http_client = await get_openrouter_llm(api_key="test-key-123")
        assert llm.openai_api_key.get_secret_value() == "test-key-123"  # type: ignore[union-attr]
        assert http_client is None

    @pytest.mark.anyio
    async def test_omits_temperature_and_max_tokens_by_default(self, mock_runtime_settings_unset: AsyncMock) -> None:
        """Test that temperature and max_completion_tokens are omitted when runtime setting is 0."""
        llm, _ = await get_openrouter_llm(api_key="test-key-123")
        assert llm.temperature is None
        assert llm.max_tokens is None

    @pytest.mark.anyio
    async def test_explicit_args_are_passed_through(self, mock_runtime_settings_unset: AsyncMock) -> None:
        """Test that explicit arguments are passed to ChatOpenAI."""
        llm, _ = await get_openrouter_llm(
            api_key="test-key-123",
            model="override/model",
            temperature=0.3,
            max_tokens=2000,
        )
        assert llm.model_name == "override/model"
        assert llm.temperature == 0.3
        assert llm.max_tokens == 2000

    @pytest.mark.anyio
    async def test_zero_temperature_allowed(self, mock_runtime_settings_unset: AsyncMock) -> None:
        """Test that temperature=0.0 is correctly handled (not treated as None)."""
        llm, _ = await get_openrouter_llm(api_key="test-key-123", temperature=0.0)
        assert llm.temperature == 0.0

    @pytest.mark.anyio
    async def test_runtime_setting_used_when_max_tokens_not_explicit(
        self, mock_runtime_settings_with_cap: AsyncMock
    ) -> None:
        """Test that agentic.max_completion_tokens runtime setting is used as fallback."""
        llm, _ = await get_openrouter_llm(api_key="test-key-123")
        assert llm.max_tokens == 4096
        mock_runtime_settings_with_cap.get_int.assert_called_once_with("agentic.max_completion_tokens")

    @pytest.mark.anyio
    async def test_runtime_settings_failure_does_not_crash(self) -> None:
        """Test that a settings infrastructure failure is handled gracefully."""
        mock_cache = AsyncMock()
        mock_cache.get_int = AsyncMock(side_effect=RuntimeError("cache down"))
        with patch(
            "syntara.agent_orchestrator.clients.openrouter_config.get_runtime_settings",
            return_value=mock_cache,
        ):
            llm, _ = await get_openrouter_llm(api_key="test-key-123")
        assert llm.max_tokens is None

    @pytest.mark.anyio
    async def test_explicit_max_tokens_overrides_runtime_setting(
        self, mock_runtime_settings_with_cap: AsyncMock
    ) -> None:
        """Test that explicit max_tokens takes precedence over runtime setting."""
        llm, _ = await get_openrouter_llm(api_key="test-key-123", max_tokens=500)
        assert llm.max_tokens == 500

    @pytest.mark.anyio
    async def test_base_url_from_credential(self, mock_runtime_settings_unset: AsyncMock) -> None:
        """Test that base_url from credential is used."""
        llm, _ = await get_openrouter_llm(api_key="test-key-123", base_url="https://custom.example.com/v1")
        assert llm.openai_api_base == "https://custom.example.com/v1"

    @pytest.mark.anyio
    async def test_default_headers_configured(
        self,
        mock_runtime_settings_unset: AsyncMock,
        override_settings: Callable[..., AbstractContextManager[object]],
    ) -> None:
        """Test that OpenRouter-specific headers are configured."""
        with override_settings(product_name="TestProduct"):
            llm, _ = await get_openrouter_llm(api_key="test-key-123")

        assert llm.default_headers is not None
        assert llm.default_headers["HTTP-Referer"] == "https://github.com/syntara-orchestration/syntara"
        assert llm.default_headers["X-Title"] == "TestProduct"

    @pytest.mark.anyio
    async def test_insecure_skip_tls_creates_http_client_with_verify_false(
        self, mock_runtime_settings_unset: AsyncMock
    ) -> None:
        """TLS skip calls build_integration_httpx_verify and wires the result into httpx.AsyncClient."""
        with patch(
            "syntara.agent_orchestrator.clients.openrouter_config.build_integration_httpx_verify",
            return_value=False,
        ) as mock_build:
            _llm, http_client = await get_openrouter_llm(
                api_key="test-key-123",
                insecure_skip_tls_verify=True,
            )
        try:
            mock_build.assert_called_once_with(insecure_skip_tls_verify=True, ca_certificate=None)
            assert http_client is not None
        finally:
            if http_client is not None:
                await http_client.aclose()

    @pytest.mark.anyio
    async def test_ca_certificate_creates_http_client_with_ssl_context(
        self, mock_runtime_settings_unset: AsyncMock, sample_ca_cert: str
    ) -> None:
        """Custom CA certificate calls build_integration_httpx_verify and wires the result into httpx.AsyncClient."""
        import ssl

        mock_ctx = ssl.create_default_context()
        with patch(
            "syntara.agent_orchestrator.clients.openrouter_config.build_integration_httpx_verify",
            return_value=mock_ctx,
        ) as mock_build:
            _llm, http_client = await get_openrouter_llm(
                api_key="test-key-123",
                ca_certificate=sample_ca_cert,
            )
        try:
            mock_build.assert_called_once_with(
                insecure_skip_tls_verify=False,
                ca_certificate=sample_ca_cert,
            )
            assert http_client is not None
        finally:
            if http_client is not None:
                await http_client.aclose()

    @pytest.mark.anyio
    async def test_no_tls_params_returns_no_http_client(self, mock_runtime_settings_unset: AsyncMock) -> None:
        """Without TLS params, http_client is None (default verify used)."""
        _, http_client = await get_openrouter_llm(api_key="test-key-123")
        assert http_client is None

    @pytest.mark.anyio
    async def test_error_message_references_credential_system(self) -> None:
        """Test that error message directs users to credential configuration."""
        with pytest.raises(LLMConfigurationError, match="Attach an LLM Provider credential"):
            await get_openrouter_llm()
