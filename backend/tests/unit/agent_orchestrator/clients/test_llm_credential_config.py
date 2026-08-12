"""Unit tests for LLMCredentialConfig."""

import pytest
from pydantic import SecretStr, ValidationError

from syntara.agent_orchestrator.models.llm_credential_config import LLMCredentialConfig


class TestLLMCredentialConfig:
    """Tests for LLMCredentialConfig frozen SQLModel."""

    def test_create_config(self) -> None:
        """Config stores all fields."""
        config = LLMCredentialConfig(
            api_key="sk-123", base_url="https://api.example.com", model="gpt-4", provider_hint="openai"
        )
        assert config.api_key.get_secret_value() == "sk-123"
        assert config.base_url == "https://api.example.com"
        assert config.model == "gpt-4"
        assert config.provider_hint == "openai"

    def test_provider_hint_defaults_to_none(self) -> None:
        """provider_hint is optional and defaults to None."""
        config = LLMCredentialConfig(api_key="sk-123", base_url="https://api.example.com", model="gpt-4")
        assert config.provider_hint is None

    def test_frozen_immutability(self) -> None:
        """Frozen SQLModel rejects attribute assignment."""
        config = LLMCredentialConfig(api_key="sk-123", base_url="https://api.example.com", model="gpt-4")
        with pytest.raises(ValidationError):
            config.api_key = SecretStr("new-key")

    def test_tls_fields_default_values(self) -> None:
        """TLS fields default to safe values when not specified."""
        config = LLMCredentialConfig(api_key="sk-123", base_url="https://api.example.com", model="gpt-4")
        assert config.insecure_skip_tls_verify is False
        assert config.ca_certificate is None

    def test_tls_fields_explicit_values(self) -> None:
        """TLS fields can be set explicitly."""
        config = LLMCredentialConfig(
            api_key="sk-123",
            base_url="https://api.example.com",
            model="gpt-4",
            insecure_skip_tls_verify=True,
            ca_certificate="-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----",
        )
        assert config.insecure_skip_tls_verify is True
        assert config.ca_certificate is not None

    def test_importable_from_models_package(self) -> None:
        """LLMCredentialConfig is re-exported from the models package."""
        from syntara.agent_orchestrator.models import LLMCredentialConfig as Imported

        assert Imported is LLMCredentialConfig
