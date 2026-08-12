"""Tests for the integration adapter protocol, result types, and factory."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from syntara.integrations.adapters.factory import (
    _clear_registry,
    create_health_check_adapter,
    register_health_check_adapter,
)
from syntara.integrations.adapters.protocol import (
    DiscoveredLLMModel,
    DiscoveredTool,
    DiscoverResult,
    HealthCheckErrorType,
    IntegrationAdapter,
    ValidateResult,
)
from syntara.integrations.exceptions import AdapterNotRegisteredError
from syntara.integrations.models.integration import IntegrationType
from syntara.integrations.models.integration_configuration import (
    LLMProviderConfiguration,
    MCPServerConfiguration,
)

# ---------------------------------------------------------------------------
# Stub adapters for testing — demonstrate the full protocol pattern
# ---------------------------------------------------------------------------


class StubLLMAdapter:
    """Stub adapter that implements the Protocol with LLM config."""

    def __init__(self, config: LLMProviderConfiguration) -> None:
        """Initialize with LLM provider configuration."""
        self.config = config

    async def validate(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> ValidateResult:
        return ValidateResult(success=True, checked_at=datetime.now(UTC))

    async def discover(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> DiscoverResult:
        return DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=[
                DiscoveredLLMModel(id="gpt-4", name="GPT-4"),
            ],
        )


class StubMCPAdapter:
    """Stub adapter that implements the Protocol with MCP config."""

    def __init__(self, config: MCPServerConfiguration) -> None:
        """Initialize with MCP server configuration."""
        self.config = config

    async def validate(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> ValidateResult:
        return ValidateResult(success=True, checked_at=datetime.now(UTC))

    async def discover(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> DiscoverResult:
        return DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_tools=[DiscoveredTool(name="search", description="Search tool")],
        )


class StubFailingAdapter:
    """Stub adapter that returns an error result."""

    def __init__(self, config: LLMProviderConfiguration) -> None:
        """Initialize with LLM provider configuration."""
        self.config = config

    async def validate(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> ValidateResult:
        return ValidateResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Invalid API key",
            error_type=HealthCheckErrorType.AUTH_FAILURE,
        )

    async def discover(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> DiscoverResult:
        return DiscoverResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Invalid API key",
            error_type=HealthCheckErrorType.AUTH_FAILURE,
        )


class NotAnAdapter:
    """A class that does not implement the Protocol."""

    async def some_other_method(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Protocol tests
# ---------------------------------------------------------------------------


class TestIntegrationAdapterProtocol:
    """Tests for IntegrationAdapter protocol conformance."""

    def test_conforming_class_is_instance(self) -> None:
        adapter = StubLLMAdapter(LLMProviderConfiguration(base_url="https://api.openai.com", provider_hint="openai"))
        assert isinstance(adapter, IntegrationAdapter)

    def test_non_conforming_class_is_not_instance(self) -> None:
        obj = NotAnAdapter()
        assert not isinstance(obj, IntegrationAdapter)

    def test_stub_mcp_adapter_is_instance(self) -> None:
        adapter = StubMCPAdapter(MCPServerConfiguration(base_url="http://localhost:8080"))
        assert isinstance(adapter, IntegrationAdapter)


# ---------------------------------------------------------------------------
# Result type tests
# ---------------------------------------------------------------------------


class TestValidateResult:
    """Tests for ValidateResult construction."""

    def test_success_result(self) -> None:
        now = datetime.now(UTC)
        result = ValidateResult(success=True, checked_at=now)
        assert result.success is True
        assert result.checked_at == now
        assert result.error is None
        assert result.error_type is None

    def test_error_result_with_classification(self) -> None:
        result = ValidateResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Connection refused",
            error_type=HealthCheckErrorType.CONNECTION_ERROR,
        )
        assert result.success is False
        assert result.error == "Connection refused"
        assert result.error_type == HealthCheckErrorType.CONNECTION_ERROR

    def test_timeout_error(self) -> None:
        result = ValidateResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Health check timed out after 10s",
            error_type=HealthCheckErrorType.TIMEOUT,
        )
        assert result.error_type == HealthCheckErrorType.TIMEOUT


class TestDiscoverResult:
    """Tests for DiscoverResult construction."""

    def test_success_result_with_tools(self) -> None:
        result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_tools=[DiscoveredTool(name="search")],
        )
        assert result.success is True
        assert result.discovered_tools is not None
        assert len(result.discovered_tools) == 1
        assert result.discovered_tools[0].name == "search"

    def test_result_with_discovered_models(self) -> None:
        models = [
            DiscoveredLLMModel(id="gpt-4", name="GPT-4"),
            DiscoveredLLMModel(id="gpt-4o", name="GPT-4o", description="Optimized GPT-4"),
        ]
        result = DiscoverResult(
            success=True,
            checked_at=datetime.now(UTC),
            discovered_models=models,
        )
        assert result.discovered_models is not None
        assert len(result.discovered_models) == 2
        assert result.discovered_models[0].id == "gpt-4"
        assert result.discovered_models[1].description == "Optimized GPT-4"

    def test_error_result(self) -> None:
        result = DiscoverResult(
            success=False,
            checked_at=datetime.now(UTC),
            error="Connection failed",
            error_type=HealthCheckErrorType.CONNECTION_ERROR,
        )
        assert result.success is False
        assert result.error == "Connection failed"
        assert result.discovered_tools is None


class TestHealthCheckErrorType:
    """Tests for HealthCheckErrorType enum."""

    def test_enum_values(self) -> None:
        assert HealthCheckErrorType.AUTH_FAILURE.value == "auth_failure"
        assert HealthCheckErrorType.CONNECTION_ERROR.value == "connection_error"
        assert HealthCheckErrorType.RATE_LIMIT.value == "rate_limit"
        assert HealthCheckErrorType.SSL_ERROR.value == "ssl_error"
        assert HealthCheckErrorType.TIMEOUT.value == "timeout"


class TestDiscoveredLLMModel:
    """Tests for DiscoveredLLMModel construction."""

    def test_required_fields(self) -> None:
        model = DiscoveredLLMModel(id="gpt-4", name="GPT-4")
        assert model.id == "gpt-4"
        assert model.name == "GPT-4"
        assert model.description is None

    def test_all_fields(self) -> None:
        model = DiscoveredLLMModel(
            id="claude-4",
            name="Claude 4",
            description="Anthropic Claude 4",
        )
        assert model.description == "Anthropic Claude 4"


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


class TestAdapterFactory:
    """Tests for adapter registry and factory dispatch."""

    @pytest.fixture(autouse=True)
    def _clean_registry(self) -> None:
        """Ensure a clean registry for each test."""
        _clear_registry()

    def test_register_and_create_adapter(self) -> None:
        register_health_check_adapter(
            IntegrationType.LLM_PROVIDER,
            lambda c: StubLLMAdapter(c),
        )

        config = LLMProviderConfiguration(base_url="https://api.openai.com", provider_hint="openai")
        adapter = create_health_check_adapter(IntegrationType.LLM_PROVIDER, config)

        assert isinstance(adapter, StubLLMAdapter)
        assert isinstance(adapter, IntegrationAdapter)
        assert adapter.config == config

    def test_create_raises_for_unregistered_type(self) -> None:
        config = LLMProviderConfiguration(base_url="https://api.openai.com", provider_hint="openai")

        with pytest.raises(AdapterNotRegisteredError, match="No health check adapter registered"):
            create_health_check_adapter(IntegrationType.LLM_PROVIDER, config)

    def test_duplicate_registration_raises(self) -> None:
        register_health_check_adapter(
            IntegrationType.LLM_PROVIDER,
            lambda c: StubLLMAdapter(c),
        )

        with pytest.raises(ValueError, match="already registered"):
            register_health_check_adapter(
                IntegrationType.LLM_PROVIDER,
                lambda c: StubLLMAdapter(c),
            )

    def test_multiple_types_registered(self) -> None:
        register_health_check_adapter(
            IntegrationType.LLM_PROVIDER,
            lambda c: StubLLMAdapter(c),
        )
        register_health_check_adapter(
            IntegrationType.MCP_SERVER,
            lambda c: StubMCPAdapter(c),
        )

        llm_config = LLMProviderConfiguration(base_url="https://api.openai.com", provider_hint="openai")
        mcp_config = MCPServerConfiguration(base_url="http://localhost:8080")

        llm_adapter = create_health_check_adapter(IntegrationType.LLM_PROVIDER, llm_config)
        mcp_adapter = create_health_check_adapter(IntegrationType.MCP_SERVER, mcp_config)

        assert isinstance(llm_adapter, StubLLMAdapter)
        assert isinstance(mcp_adapter, StubMCPAdapter)


# ---------------------------------------------------------------------------
# End-to-end pattern test
# ---------------------------------------------------------------------------


class TestFullAdapterPattern:
    """Demonstrates the complete flow: factory → adapter → result."""

    @pytest.fixture(autouse=True)
    def _clean_registry(self) -> None:
        _clear_registry()

    @pytest.mark.asyncio
    async def test_successful_discover_with_models(self) -> None:
        register_health_check_adapter(
            IntegrationType.LLM_PROVIDER,
            lambda c: StubLLMAdapter(c),
        )

        config = LLMProviderConfiguration(
            base_url="https://api.openai.com",
            provider_hint="openai",
        )
        adapter = create_health_check_adapter(IntegrationType.LLM_PROVIDER, config)

        result = await adapter.discover(
            resolved_credential={"llm_api_key": "sk-test-key"},
            timeout_seconds=10,
        )

        assert result.success is True
        assert result.discovered_models is not None
        assert len(result.discovered_models) == 1
        assert result.discovered_models[0].id == "gpt-4"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_failed_discover_with_error_type(self) -> None:
        register_health_check_adapter(
            IntegrationType.LLM_PROVIDER,
            lambda c: StubFailingAdapter(c),
        )

        config = LLMProviderConfiguration(base_url="https://api.openai.com", provider_hint="openai")
        adapter = create_health_check_adapter(IntegrationType.LLM_PROVIDER, config)

        result = await adapter.discover(
            resolved_credential={"llm_api_key": "bad-key"},
            timeout_seconds=10,
        )

        assert result.success is False
        assert result.error == "Invalid API key"
        assert result.error_type == HealthCheckErrorType.AUTH_FAILURE
        assert result.discovered_models is None

    @pytest.mark.asyncio
    async def test_successful_validate(self) -> None:
        register_health_check_adapter(
            IntegrationType.LLM_PROVIDER,
            lambda c: StubLLMAdapter(c),
        )

        config = LLMProviderConfiguration(base_url="https://api.openai.com", provider_hint="openai")
        adapter = create_health_check_adapter(IntegrationType.LLM_PROVIDER, config)

        result = await adapter.validate(
            resolved_credential={"llm_api_key": "sk-test-key"},
            timeout_seconds=10,
        )

        assert result.success is True
        assert result.error is None
