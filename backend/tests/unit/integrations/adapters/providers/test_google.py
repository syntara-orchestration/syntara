"""Tests for GoogleProvider."""

from syntara.integrations.adapters.providers.google import GoogleProvider


class TestGoogleProvider:
    """Tests for URL construction, headers, and response parsing."""

    def test_default_base_url(self) -> None:
        provider = GoogleProvider()
        assert provider.default_base_url == "https://generativelanguage.googleapis.com/v1"

    def test_build_headers_uses_x_goog_api_key(self) -> None:
        """Google uses x-goog-api-key header for auth."""
        provider = GoogleProvider()
        headers = provider.build_headers("gemini-key")
        assert headers == {"x-goog-api-key": "gemini-key"}

    def test_parse_models_response(self) -> None:
        provider = GoogleProvider()
        json_data = {
            "models": [
                {
                    "name": "models/gemini-2.0-flash",
                    "displayName": "Gemini 2.0 Flash",
                    "description": "Fast and efficient",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 8192,
                },
                {
                    "name": "models/gemini-2.0-pro",
                    "displayName": "Gemini 2.0 Pro",
                    "description": "Advanced reasoning",
                    "inputTokenLimit": 1048576,
                    "outputTokenLimit": 8192,
                },
            ]
        }
        models = provider.parse_models_response(json_data)
        assert len(models) == 2
        assert models[0].id == "gemini-2.0-flash"
        assert models[0].name == "Gemini 2.0 Flash"
        assert models[0].description == "Fast and efficient"
        assert models[1].id == "gemini-2.0-pro"
        assert models[1].name == "Gemini 2.0 Pro"

    def test_parse_models_response_fallback_name(self) -> None:
        """If displayName is missing, falls back to name."""
        provider = GoogleProvider()
        models = provider.parse_models_response({"models": [{"name": "models/gemini-flash"}]})
        assert models[0].name == "gemini-flash"

    def test_parse_models_response_skips_missing_name(self) -> None:
        """Models without a name field are skipped."""
        provider = GoogleProvider()
        models = provider.parse_models_response(
            {"models": [{"displayName": "No Name"}, {"name": "models/gemini-flash", "displayName": "Flash"}]}
        )
        assert len(models) == 1
        assert models[0].id == "gemini-flash"

    def test_parse_models_response_empty(self) -> None:
        provider = GoogleProvider()
        models = provider.parse_models_response({"models": []})
        assert models == []

    def test_parse_models_response_missing_models_key(self) -> None:
        """Missing 'models' key returns empty list (Google uses 'models' not 'data')."""
        provider = GoogleProvider()
        models = provider.parse_models_response({})
        assert models == []

    def test_parse_models_response_preserves_description(self) -> None:
        """Description field is captured from Gemini response."""
        provider = GoogleProvider()
        models = provider.parse_models_response(
            {"models": [{"name": "models/x", "displayName": "X", "description": "A model"}]}
        )
        assert models[0].description == "A model"

    def test_parse_models_response_no_description(self) -> None:
        """Missing description results in None."""
        provider = GoogleProvider()
        models = provider.parse_models_response({"models": [{"name": "models/x", "displayName": "X"}]})
        assert models[0].description is None

    def test_next_page_params_with_token(self) -> None:
        provider = GoogleProvider()
        result = provider.next_page_params({"nextPageToken": "abc123"})
        assert result == {"pageToken": "abc123"}

    def test_next_page_params_no_token(self) -> None:
        provider = GoogleProvider()
        assert provider.next_page_params({}) is None

    def test_next_page_params_empty_token(self) -> None:
        provider = GoogleProvider()
        assert provider.next_page_params({"nextPageToken": ""}) is None
