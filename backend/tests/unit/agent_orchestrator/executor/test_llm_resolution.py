"""Unit tests for InvocationExecutor LLM resolution methods.

Tests _resolve_llm_model_and_integration and _resolve_llm_api_key
covering happy paths and error branches (invalid UUID, not found, disabled, wrong type).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from syntara.agent_orchestrator.exceptions import LLMConfigurationError
from syntara.agent_orchestrator.executor.invocation_executor import InvocationExecutor
from syntara.integrations.models.integration import Integration
from syntara.integrations.models.integration_configuration import LLMProviderConfiguration, LLMProviderHint
from syntara.integrations.models.llm_model import LLMModel


def _make_executor(mock_session: MagicMock | None = None) -> tuple[InvocationExecutor, MagicMock]:
    """Build a minimal InvocationExecutor with a controllable mock session."""
    session = mock_session or MagicMock()

    @asynccontextmanager
    async def mock_session_ctx() -> AsyncGenerator[MagicMock, None]:
        yield session

    executor = InvocationExecutor.__new__(InvocationExecutor)
    executor.get_async_session_context = mock_session_ctx
    executor.session_factory = mock_session_ctx  # type: ignore[assignment]
    return executor, session


def _mock_model_and_integration(
    *,
    model_enabled: bool = True,
    integration_enabled: bool = True,
    base_url: str | None = "https://api.openai.com/v1",
    provider_hint: LLMProviderHint = LLMProviderHint.OPENAI,
    model_id: str = "gpt-4o",
    integration_config: object | None = None,
) -> tuple[MagicMock, MagicMock]:
    """Create mock LLMModel and Integration for session.get dispatch."""
    integration_uuid = uuid4()

    mock_model = MagicMock()
    mock_model.integration_id = integration_uuid
    mock_model.model_id = model_id
    mock_model.enabled = model_enabled

    if integration_config is None:
        config_kwargs: dict[str, object] = {
            "integration_type": "llm_provider",
            "provider_hint": provider_hint,
        }
        if base_url:
            config_kwargs["base_url"] = base_url
        integration_config = LLMProviderConfiguration(**config_kwargs)

    mock_integration = MagicMock()
    mock_integration.enabled = integration_enabled
    mock_integration.configuration = integration_config

    return mock_model, mock_integration


def _session_get_dispatch(mock_model: MagicMock, mock_integration: MagicMock | None) -> AsyncMock:
    """Build a session.get side_effect that dispatches by model class."""

    async def _get(model_class: type, pk: object) -> object | None:
        if model_class is LLMModel:
            return mock_model
        if model_class is Integration:
            return mock_integration
        return None

    return AsyncMock(side_effect=_get)


class TestResolveLlmModelAndIntegration:
    """Tests for _resolve_llm_model_and_integration."""

    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        executor, session = _make_executor()
        mock_model, mock_integration = _mock_model_and_integration()
        session.get = _session_get_dispatch(mock_model, mock_integration)

        model_id, base_url, provider_hint, skip_tls, ca_cert = await executor._resolve_llm_model_and_integration(
            str(uuid4())
        )

        assert model_id == "gpt-4o"
        assert base_url == "https://api.openai.com/v1"
        assert provider_hint == "openai"
        assert skip_tls is False
        assert ca_cert is None

    @pytest.mark.asyncio
    async def test_happy_path_no_base_url(self) -> None:
        executor, session = _make_executor()
        mock_model, mock_integration = _mock_model_and_integration(base_url=None)
        session.get = _session_get_dispatch(mock_model, mock_integration)

        model_id, base_url, provider_hint, skip_tls, ca_cert = await executor._resolve_llm_model_and_integration(
            str(uuid4())
        )

        assert model_id == "gpt-4o"
        assert base_url is None
        assert provider_hint == "openai"
        assert skip_tls is False
        assert ca_cert is None

    @pytest.mark.asyncio
    async def test_invalid_model_uuid(self) -> None:
        executor, _ = _make_executor()

        with pytest.raises(LLMConfigurationError, match="Invalid LLM model ID"):
            await executor._resolve_llm_model_and_integration("not-a-uuid")

    @pytest.mark.asyncio
    async def test_model_not_found(self) -> None:
        executor, session = _make_executor()
        session.get = AsyncMock(return_value=None)

        model_id = str(uuid4())
        with pytest.raises(LLMConfigurationError, match="not found"):
            await executor._resolve_llm_model_and_integration(model_id)

    @pytest.mark.asyncio
    async def test_model_disabled(self) -> None:
        executor, session = _make_executor()
        mock_model, mock_integration = _mock_model_and_integration(model_enabled=False)
        session.get = _session_get_dispatch(mock_model, mock_integration)

        model_id = str(uuid4())
        with pytest.raises(LLMConfigurationError, match="disabled"):
            await executor._resolve_llm_model_and_integration(model_id)

    @pytest.mark.asyncio
    async def test_integration_not_found(self) -> None:
        executor, session = _make_executor()
        mock_model, _ = _mock_model_and_integration()
        session.get = _session_get_dispatch(mock_model, None)

        model_id = str(uuid4())
        with pytest.raises(LLMConfigurationError, match="not found"):
            await executor._resolve_llm_model_and_integration(model_id)

    @pytest.mark.asyncio
    async def test_integration_disabled(self) -> None:
        executor, session = _make_executor()
        mock_model, mock_integration = _mock_model_and_integration(integration_enabled=False)
        session.get = _session_get_dispatch(mock_model, mock_integration)

        model_id = str(uuid4())
        with pytest.raises(LLMConfigurationError, match="disabled"):
            await executor._resolve_llm_model_and_integration(model_id)

    @pytest.mark.asyncio
    async def test_not_llm_provider(self) -> None:
        executor, session = _make_executor()
        mock_model, mock_integration = _mock_model_and_integration(
            integration_config=MagicMock(spec=[]),
        )
        session.get = _session_get_dispatch(mock_model, mock_integration)

        model_id = str(uuid4())
        with pytest.raises(LLMConfigurationError, match="not an LLM provider"):
            await executor._resolve_llm_model_and_integration(model_id)


class TestResolveLlmApiKey:
    """Tests for _resolve_llm_api_key."""

    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        executor, session = _make_executor()
        cred_uuid = uuid4()

        mock_credential = MagicMock()
        mock_credential.enabled = True
        mock_credential.secret_id = uuid4()
        mock_credential.credential_type_id = uuid4()

        mock_cred_type = MagicMock()
        mock_cred_type.injectors = {}

        async def mock_get(model_class: type, pk: object) -> object:
            from syntara.credentials.models.credential import Credential
            from syntara.credentials.models.credential_type import CredentialType

            if model_class is Credential:
                return mock_credential
            if model_class is CredentialType:
                return mock_cred_type
            return None

        session.get = AsyncMock(side_effect=mock_get)

        mock_resolved = MagicMock()
        mock_resolved.extra_vars = {"llm_api_key": "sk-test-key-123"}

        with (
            patch("syntara.agent_orchestrator.executor.invocation_executor.create_secret_service") as mock_secret_svc,
            patch("syntara.agent_orchestrator.executor.invocation_executor.InjectorResolver") as mock_injector,
        ):
            mock_secret_svc.return_value.retrieve_secret = AsyncMock(return_value={"api_key": "encrypted"})
            mock_injector.resolve.return_value = mock_resolved

            result = await executor._resolve_llm_api_key(str(cred_uuid))

        assert result == "sk-test-key-123"

    @pytest.mark.asyncio
    async def test_invalid_uuid(self) -> None:
        executor, _ = _make_executor()

        with pytest.raises(LLMConfigurationError, match="Invalid LLM credential ID"):
            await executor._resolve_llm_api_key("not-a-uuid")

    @pytest.mark.asyncio
    async def test_not_found(self) -> None:
        executor, session = _make_executor()
        session.get = AsyncMock(return_value=None)

        cred_id = str(uuid4())
        with pytest.raises(LLMConfigurationError, match="not found"):
            await executor._resolve_llm_api_key(cred_id)

    @pytest.mark.asyncio
    async def test_disabled(self) -> None:
        executor, session = _make_executor()

        mock_credential = MagicMock()
        mock_credential.enabled = False
        session.get = AsyncMock(return_value=mock_credential)

        cred_id = str(uuid4())
        with pytest.raises(LLMConfigurationError, match="disabled"):
            await executor._resolve_llm_api_key(cred_id)

    @pytest.mark.asyncio
    async def test_no_secret_id(self) -> None:
        executor, session = _make_executor()

        mock_credential = MagicMock()
        mock_credential.enabled = True
        mock_credential.secret_id = None
        session.get = AsyncMock(return_value=mock_credential)

        cred_id = str(uuid4())
        with pytest.raises(LLMConfigurationError, match="no stored secret"):
            await executor._resolve_llm_api_key(cred_id)

    @pytest.mark.asyncio
    async def test_decryption_failure(self) -> None:
        executor, session = _make_executor()

        mock_credential = MagicMock()
        mock_credential.enabled = True
        mock_credential.secret_id = uuid4()
        session.get = AsyncMock(return_value=mock_credential)

        cred_id = str(uuid4())
        with patch("syntara.agent_orchestrator.executor.invocation_executor.create_secret_service") as mock_secret_svc:
            mock_secret_svc.return_value.retrieve_secret = AsyncMock(side_effect=RuntimeError("decrypt failed"))

            with pytest.raises(LLMConfigurationError, match=r"Failed to decrypt.*key rotation"):
                await executor._resolve_llm_api_key(cred_id)

    @pytest.mark.asyncio
    async def test_credential_type_not_found(self) -> None:
        executor, session = _make_executor()

        mock_credential = MagicMock()
        mock_credential.enabled = True
        mock_credential.secret_id = uuid4()
        mock_credential.credential_type_id = uuid4()

        async def mock_get(model_class: type, pk: object) -> object:
            from syntara.credentials.models.credential import Credential

            if model_class is Credential:
                return mock_credential
            return None

        session.get = AsyncMock(side_effect=mock_get)

        cred_id = str(uuid4())
        with patch("syntara.agent_orchestrator.executor.invocation_executor.create_secret_service") as mock_secret_svc:
            mock_secret_svc.return_value.retrieve_secret = AsyncMock(return_value={"api_key": "encrypted"})

            with pytest.raises(LLMConfigurationError, match="Credential type for"):
                await executor._resolve_llm_api_key(cred_id)

    @pytest.mark.asyncio
    async def test_injector_resolution_failure(self) -> None:
        executor, session = _make_executor()

        mock_credential = MagicMock()
        mock_credential.enabled = True
        mock_credential.secret_id = uuid4()
        mock_credential.credential_type_id = uuid4()

        mock_cred_type = MagicMock()
        mock_cred_type.injectors = {}

        async def mock_get(model_class: type, pk: object) -> object:
            from syntara.credentials.models.credential import Credential
            from syntara.credentials.models.credential_type import CredentialType

            if model_class is Credential:
                return mock_credential
            if model_class is CredentialType:
                return mock_cred_type
            return None

        session.get = AsyncMock(side_effect=mock_get)

        cred_id = str(uuid4())
        with (
            patch("syntara.agent_orchestrator.executor.invocation_executor.create_secret_service") as mock_secret_svc,
            patch("syntara.agent_orchestrator.executor.invocation_executor.InjectorResolver") as mock_injector,
        ):
            mock_secret_svc.return_value.retrieve_secret = AsyncMock(return_value={"api_key": "encrypted"})
            mock_injector.resolve.side_effect = RuntimeError("template error")

            with pytest.raises(LLMConfigurationError, match="Failed to resolve"):
                await executor._resolve_llm_api_key(cred_id)

    @pytest.mark.asyncio
    async def test_no_api_key_in_resolved(self) -> None:
        executor, session = _make_executor()

        mock_credential = MagicMock()
        mock_credential.enabled = True
        mock_credential.secret_id = uuid4()
        mock_credential.credential_type_id = uuid4()

        mock_cred_type = MagicMock()
        mock_cred_type.injectors = {}

        async def mock_get(model_class: type, pk: object) -> object:
            from syntara.credentials.models.credential import Credential
            from syntara.credentials.models.credential_type import CredentialType

            if model_class is Credential:
                return mock_credential
            if model_class is CredentialType:
                return mock_cred_type
            return None

        session.get = AsyncMock(side_effect=mock_get)

        mock_resolved = MagicMock()
        mock_resolved.extra_vars = {}  # no llm_api_key

        cred_id = str(uuid4())
        with (
            patch("syntara.agent_orchestrator.executor.invocation_executor.create_secret_service") as mock_secret_svc,
            patch("syntara.agent_orchestrator.executor.invocation_executor.InjectorResolver") as mock_injector,
        ):
            mock_secret_svc.return_value.retrieve_secret = AsyncMock(return_value={"api_key": "encrypted"})
            mock_injector.resolve.return_value = mock_resolved

            with pytest.raises(LLMConfigurationError, match="contains no API key"):
                await executor._resolve_llm_api_key(cred_id)
