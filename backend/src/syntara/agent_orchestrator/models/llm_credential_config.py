"""Lightweight credential config for threading LLM credentials through service layers."""

from typing import ClassVar

from pydantic import ConfigDict, SecretStr
from sqlmodel import Field, SQLModel


class LLMCredentialConfig(SQLModel):
    """Immutable credential config carrying api_key, base_url, and model through the call chain.

    Each service creates its own LLM instance with these shared credentials
    but independent temperature/max_tokens settings.
    """

    model_config: ClassVar[ConfigDict] = ConfigDict(frozen=True)  # type: ignore[assignment]

    api_key: SecretStr = Field(...)
    base_url: str = Field(...)
    model: str = Field(...)
    provider_hint: str | None = Field(default=None)
    insecure_skip_tls_verify: bool = Field(default=False)
    ca_certificate: str | None = Field(default=None)
