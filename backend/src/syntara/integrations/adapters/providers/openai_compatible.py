"""OpenAI-compatible provider (OpenAI, Red Hat AI, Custom)."""

from __future__ import annotations

from typing import Any

from syntara.integrations.adapters.protocol import DiscoveredLLMModel
from syntara.integrations.adapters.providers.base import LLMProviderBase


class OpenAICompatibleProvider(LLMProviderBase):
    """Provider for OpenAI-compatible APIs (OpenAI, Red Hat AI, Custom/vLLM/LiteLLM).

    Auth: ``Authorization: Bearer {api_key}``
    Models endpoint: ``GET {base_url}/models``
    Response format::

        { "data": [{ "id": "gpt-4o", "object": "model", "created": 1686935002, "owned_by": "openai" }] }

    Only ``id`` is used; OpenAI does not return display names or descriptions.
    """

    def __init__(self, *, default_url: str | None = "https://api.openai.com/v1") -> None:
        """Initialize with optional default URL.

        Args:
            default_url: Default base URL for this provider instance.
                Set to None for providers that require a user-provided URL
                (Red Hat AI, Custom).

        """
        self._default_url = default_url

    @property
    def default_base_url(self) -> str | None:
        """Default base URL."""
        return self._default_url

    def build_headers(self, api_key: str) -> dict[str, str]:
        """Build Bearer auth headers."""
        return {"Authorization": f"Bearer {api_key}"}

    def parse_models_response(self, json_data: dict[str, Any]) -> list[DiscoveredLLMModel]:
        """Parse OpenAI-format response.

        Reads ``data[]`` array. Each model has ``id`` only — name is set
        equal to id since OpenAI does not return display names.
        Models missing an ``id`` field are skipped.
        """
        return [
            DiscoveredLLMModel(
                id=m["id"],
                name=m.get("id", ""),
            )
            for m in json_data.get("data", [])
            if m.get("id")
        ]
