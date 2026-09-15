"""Abstract base class for LLM provider implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from syntara.integrations.adapters.protocol import DiscoveredLLMModel


class LLMProviderBase(ABC):
    """Base class for LLM provider-specific behavior.

    Each provider implements URL construction, authentication headers,
    and response parsing. The LLMProviderAdapter delegates to the
    appropriate provider instance based on LLMProviderHint.
    """

    @property
    @abstractmethod
    def default_base_url(self) -> str | None:
        """Default base URL for this provider, or None if user must provide one."""
        ...

    @abstractmethod
    def build_headers(self, api_key: str) -> dict[str, str]:
        """Build request headers for the models listing request."""
        ...

    @abstractmethod
    def parse_models_response(self, json_data: dict[str, Any]) -> list[DiscoveredLLMModel]:
        """Parse the provider's JSON response into DiscoveredLLMModel list."""
        ...

    # ── Concrete defaults — override only when a provider deviates ──

    @property
    def models_endpoint(self) -> str:
        """Path appended to base_url to list models. Override for non-OpenAI layouts."""
        return "/models"

    def resolve_api_key(self, resolved_credential: dict[str, Any]) -> str | None:
        """Extract API key from credential extra_vars. Override for non-standard key names."""
        return resolved_credential.get("llm_api_key")

    def build_models_url(self, base_url: str) -> str:
        """Build the full models listing URL. Override for custom paths."""
        return f"{base_url.rstrip('/')}{self.models_endpoint}"

    @property
    def credential_confirmation_path(self) -> str | None:
        """Auth-gated path used to prove the API key after a catalog 200.

        ``GET {base_url}{path}`` must return 401/403 for a rejected key.
        ``None`` means the models listing is already the credential check
        (Anthropic, Gemini). Used by ``validate()`` only. A 404/405/501 on
        this path is treated as "endpoint absent" and the models listing
        result is trusted.
        """
        return None

    def build_credential_confirmation_url(self, base_url: str) -> str | None:
        """Build the credential-confirmation URL, or None if the provider has no probe."""
        path = self.credential_confirmation_path
        if not path:
            return None
        return f"{base_url.rstrip('/')}{path}"

    def next_page_params(self, json_data: dict[str, Any]) -> dict[str, str] | None:  # noqa: ARG002
        """Return query params for the next page, or None if done. Default: single-page."""
        return None
