"""Tests for LLMProviderBase concrete defaults."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from syntara.integrations.adapters.providers.base import LLMProviderBase

if TYPE_CHECKING:
    from syntara.integrations.adapters.protocol import DiscoveredLLMModel


class _ConcreteProvider(LLMProviderBase):
    """Minimal concrete subclass to test base class defaults."""

    @property
    def default_base_url(self) -> str:
        return "https://example.com"

    def build_headers(self, api_key: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {api_key}"}

    def parse_models_response(self, json_data: dict[str, Any]) -> list[DiscoveredLLMModel]:
        return []


class TestLLMProviderBaseDefaults:
    """Tests for the concrete default methods on LLMProviderBase."""

    def test_models_endpoint(self) -> None:
        provider = _ConcreteProvider()
        assert provider.models_endpoint == "/models"

    def test_resolve_api_key(self) -> None:
        provider = _ConcreteProvider()
        assert provider.resolve_api_key({"llm_api_key": "sk-test"}) == "sk-test"

    def test_resolve_api_key_missing(self) -> None:
        provider = _ConcreteProvider()
        assert provider.resolve_api_key({}) is None

    def test_build_models_url(self) -> None:
        provider = _ConcreteProvider()
        assert provider.build_models_url("https://api.example.com/v1") == "https://api.example.com/v1/models"

    def test_build_models_url_strips_trailing_slash(self) -> None:
        provider = _ConcreteProvider()
        assert provider.build_models_url("https://api.example.com/v1/") == "https://api.example.com/v1/models"

    def test_next_page_params_returns_none(self) -> None:
        provider = _ConcreteProvider()
        assert provider.next_page_params({"some": "data"}) is None

    def test_next_page_params_empty_dict(self) -> None:
        provider = _ConcreteProvider()
        assert provider.next_page_params({}) is None

    def test_credential_confirmation_path_default_none(self) -> None:
        provider = _ConcreteProvider()
        assert provider.credential_confirmation_path is None
        assert provider.build_credential_confirmation_url("https://api.example.com/v1") is None
