"""Anthropic provider."""

from __future__ import annotations

from typing import Any

from syntara.integrations.adapters.protocol import DiscoveredLLMModel
from syntara.integrations.adapters.providers.base import LLMProviderBase

_ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(LLMProviderBase):
    """Provider for the Anthropic Messages API.

    Auth: ``x-api-key: {api_key}`` + ``anthropic-version: 2023-06-01``
    Models endpoint: ``GET https://api.anthropic.com/v1/models``
    Response format::

        { "data": [{ "id": "claude-opus-4-6", "display_name": "Claude Opus 4.6",
                      "created_at": "...", "max_input_tokens": 200000, "max_tokens": 4096 }] }

    Uses ``display_name`` for the human-readable name (falls back to ``id``).
    """

    @property
    def default_base_url(self) -> str:
        """Default base URL."""
        return "https://api.anthropic.com/v1"

    def build_headers(self, api_key: str) -> dict[str, str]:
        """Build Anthropic-specific auth headers."""
        return {
            "x-api-key": api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
        }

    def next_page_params(self, json_data: dict[str, Any]) -> dict[str, str] | None:
        """Return pagination params for Anthropic's model listing.

        Anthropic signals more pages via ``has_more: true`` and provides
        ``last_id`` as the cursor for the next request (``?after=<last_id>``).
        """
        if json_data.get("has_more") and json_data.get("last_id"):
            return {"after": json_data["last_id"]}
        return None

    def parse_models_response(self, json_data: dict[str, Any]) -> list[DiscoveredLLMModel]:
        """Parse Anthropic response format.

        Reads ``data[]`` array. Uses ``display_name`` for human-readable
        name, falling back to ``id`` if absent.
        """
        return [
            DiscoveredLLMModel(
                id=m["id"],
                name=m.get("display_name", m.get("id", "")),
                description=m.get("description"),
            )
            for m in json_data.get("data", [])
            if m.get("id")
        ]
