"""Google provider (Gemini API)."""

from __future__ import annotations

from typing import Any

from syntara.integrations.adapters.protocol import DiscoveredLLMModel
from syntara.integrations.adapters.providers.base import LLMProviderBase


class GoogleProvider(LLMProviderBase):
    """Provider for the Google Gemini native API (v1).

    Auth: ``x-goog-api-key: {api_key}`` header
    Models endpoint: ``GET https://generativelanguage.googleapis.com/v1/models``
    Response format::

        { "models": [{ "name": "models/gemini-2.0-flash", "displayName": "Gemini 2.0 Flash",
                        "description": "...", "inputTokenLimit": 1048576, "outputTokenLimit": 8192 }] }

    Uses ``displayName`` for human-readable name (falls back to ``name``).
    Note: response root key is ``models`` (not ``data`` like OpenAI/Anthropic).
    """

    @property
    def default_base_url(self) -> str:
        """Default base URL."""
        return "https://generativelanguage.googleapis.com/v1"

    def build_headers(self, api_key: str) -> dict[str, str]:
        """Build Google API key header."""
        return {"x-goog-api-key": api_key}

    def next_page_params(self, json_data: dict[str, Any]) -> dict[str, str] | None:
        """Return pagination params for Google's model listing.

        Google signals more pages via ``nextPageToken``. Pass it as
        ``?pageToken=<token>`` on the next request.
        """
        token = json_data.get("nextPageToken")
        if token:
            return {"pageToken": token}
        return None

    def parse_models_response(self, json_data: dict[str, Any]) -> list[DiscoveredLLMModel]:
        """Parse Gemini native response format.

        Reads ``models[]`` array (not ``data[]``). Uses ``displayName``
        for human-readable name, falling back to ``name`` if absent.
        """
        return [
            DiscoveredLLMModel(
                id=m["name"].removeprefix("models/"),
                name=m.get("displayName", m.get("name", "")).removeprefix("models/"),
                description=m.get("description"),
            )
            for m in json_data.get("models", [])
            if m.get("name")
        ]
