"""Tests for OpenAICompatibleProvider."""

from syntara.integrations.adapters.providers.openai_compatible import OpenAICompatibleProvider


class TestOpenAICompatibleProvider:
    """Tests for URL construction, headers, and response parsing."""

    def test_default_base_url(self) -> None:
        """Default provider uses api.openai.com."""
        provider = OpenAICompatibleProvider()
        assert provider.default_base_url == "https://api.openai.com/v1"

    def test_custom_default_url(self) -> None:
        """Red Hat AI / Custom providers have no default URL."""
        provider = OpenAICompatibleProvider(default_url=None)
        assert provider.default_base_url is None

    def test_build_headers_uses_bearer(self) -> None:
        provider = OpenAICompatibleProvider()
        headers = provider.build_headers("sk-test-key")
        assert headers == {"Authorization": "Bearer sk-test-key"}

    def test_parse_models_response(self) -> None:
        provider = OpenAICompatibleProvider()
        json_data = {
            "data": [
                {"id": "gpt-4o", "object": "model", "created": 1686935002, "owned_by": "openai"},
                {"id": "gpt-4o-mini", "object": "model", "created": 1686935002, "owned_by": "openai"},
            ]
        }
        models = provider.parse_models_response(json_data)
        assert len(models) == 2
        assert models[0].id == "gpt-4o"
        assert models[0].name == "gpt-4o"
        assert models[1].id == "gpt-4o-mini"

    def test_parse_models_response_empty(self) -> None:
        provider = OpenAICompatibleProvider()
        models = provider.parse_models_response({"data": []})
        assert models == []

    def test_parse_models_response_missing_data_key(self) -> None:
        """Missing 'data' key returns empty list."""
        provider = OpenAICompatibleProvider()
        models = provider.parse_models_response({})
        assert models == []

    def test_parse_models_response_name_equals_id(self) -> None:
        """OpenAI doesn't return display names — name should equal id."""
        provider = OpenAICompatibleProvider()
        models = provider.parse_models_response({"data": [{"id": "gpt-4o"}]})
        assert models[0].name == "gpt-4o"
        assert models[0].description is None

    def test_parse_models_response_skips_missing_id(self) -> None:
        """Models without an id field are skipped."""
        provider = OpenAICompatibleProvider()
        models = provider.parse_models_response({"data": [{"object": "model"}, {"id": "gpt-4o"}]})
        assert len(models) == 1
        assert models[0].id == "gpt-4o"

    def test_next_page_params_returns_none(self) -> None:
        """OpenAI does not paginate — base class default returns None."""
        provider = OpenAICompatibleProvider()
        assert provider.next_page_params({"data": [{"id": "gpt-4o"}]}) is None

    def test_credential_confirmation_path(self) -> None:
        provider = OpenAICompatibleProvider()
        assert provider.credential_confirmation_path == "/key"
        assert (
            provider.build_credential_confirmation_url("https://openrouter.ai/api/v1")
            == "https://openrouter.ai/api/v1/key"
        )
        assert (
            provider.build_credential_confirmation_url("https://openrouter.ai/api/v1/")
            == "https://openrouter.ai/api/v1/key"
        )
