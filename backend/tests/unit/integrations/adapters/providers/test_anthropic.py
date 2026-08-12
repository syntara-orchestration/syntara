"""Tests for AnthropicProvider."""

from syntara.integrations.adapters.providers.anthropic import AnthropicProvider


class TestAnthropicProvider:
    """Tests for URL construction, headers, and response parsing."""

    def test_default_base_url(self) -> None:
        provider = AnthropicProvider()
        assert provider.default_base_url == "https://api.anthropic.com/v1"

    def test_build_headers_uses_x_api_key(self) -> None:
        """Anthropic uses x-api-key header, not Bearer."""
        provider = AnthropicProvider()
        headers = provider.build_headers("sk-ant-test")
        assert headers["x-api-key"] == "sk-ant-test"
        assert "Authorization" not in headers

    def test_build_headers_includes_anthropic_version(self) -> None:
        provider = AnthropicProvider()
        headers = provider.build_headers("sk-ant-test")
        assert headers["anthropic-version"] == "2023-06-01"

    def test_parse_models_response(self) -> None:
        provider = AnthropicProvider()
        json_data = {
            "data": [
                {
                    "id": "claude-opus-4-6",
                    "display_name": "Claude Opus 4.6",
                    "created_at": "2026-02-04T00:00:00Z",
                    "type": "model",
                },
                {
                    "id": "claude-sonnet-4-6",
                    "display_name": "Claude Sonnet 4.6",
                    "created_at": "2026-02-04T00:00:00Z",
                    "type": "model",
                },
            ]
        }
        models = provider.parse_models_response(json_data)
        assert len(models) == 2
        assert models[0].id == "claude-opus-4-6"
        assert models[0].name == "Claude Opus 4.6"
        assert models[1].id == "claude-sonnet-4-6"
        assert models[1].name == "Claude Sonnet 4.6"

    def test_parse_models_response_fallback_name_to_id_to_id(self) -> None:
        """If display_name is missing, falls back to id."""
        provider = AnthropicProvider()
        models = provider.parse_models_response({"data": [{"id": "claude-4"}]})
        assert models[0].name == "claude-4"

    def test_parse_models_response_skips_missing_id(self) -> None:
        """Models without an id field are skipped."""
        provider = AnthropicProvider()
        models = provider.parse_models_response({"data": [{"display_name": "No ID"}, {"id": "claude-4"}]})
        assert len(models) == 1
        assert models[0].id == "claude-4"

    def test_parse_models_response_empty(self) -> None:
        provider = AnthropicProvider()
        models = provider.parse_models_response({"data": []})
        assert models == []

    def test_parse_models_response_missing_data_key(self) -> None:
        provider = AnthropicProvider()
        models = provider.parse_models_response({})
        assert models == []

    def test_next_page_params_has_more_with_last_id(self) -> None:
        provider = AnthropicProvider()
        result = provider.next_page_params({"has_more": True, "last_id": "model-x"})
        assert result == {"after": "model-x"}

    def test_next_page_params_no_more(self) -> None:
        provider = AnthropicProvider()
        assert provider.next_page_params({"has_more": False}) is None

    def test_next_page_params_missing_last_id(self) -> None:
        provider = AnthropicProvider()
        assert provider.next_page_params({"has_more": True}) is None

    def test_next_page_params_empty_response(self) -> None:
        provider = AnthropicProvider()
        assert provider.next_page_params({}) is None
