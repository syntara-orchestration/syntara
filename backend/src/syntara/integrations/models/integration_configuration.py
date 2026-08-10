"""Integration configuration models.

Configuration classes for different integration types.
Each configuration class defines the non-sensitive parameters for
connecting to a specific integration type. Sensitive fields (API keys,
tokens, passwords) are stored in the linked Credential, not here.
"""

import ssl
from enum import StrEnum
from typing import Annotated, ClassVar, Literal, Self

from pydantic import ConfigDict, Field, field_validator, model_validator
from sqlmodel import SQLModel

from syntara.core.lib.url_validation import validate_endpoint_url, validate_host_url


class LLMProviderHint(StrEnum):
    """LLM provider backend type."""

    RED_HAT_AI = "red_hat_ai"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    CUSTOM = "custom"


class IntegrationSecurityMixin(SQLModel):
    """Shared security fields for all integration configuration types."""

    allow_http: bool = Field(
        default=False,
        description="Allow HTTP (unencrypted) connections. Loopback addresses are always permitted over HTTP.",
    )

    insecure_skip_tls_verify: bool = Field(
        default=False,
        description="Disable TLS certificate verification for connections to this integration.",
    )

    ca_certificate: str | None = Field(
        default=None,
        description="PEM-encoded CA certificate to trust for this integration's TLS connections.",
    )

    @field_validator("ca_certificate", mode="before")
    @classmethod
    def validate_ca_certificate(cls, v: str | None) -> str | None:
        """Reject whitespace-only and unparseable PEM data at save time."""
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if "-----BEGIN CERTIFICATE-----" not in v:
            msg = "ca_certificate must be PEM-encoded (expected -----BEGIN CERTIFICATE----- marker)."
            raise ValueError(msg)
        try:
            ctx = ssl.create_default_context()
            ctx.load_verify_locations(cadata=v)
        except ssl.SSLError as e:
            msg = f"ca_certificate contains invalid PEM data: {e}"
            raise ValueError(msg) from e
        return v

    @model_validator(mode="after")
    def normalize_tls_fields(self) -> Self:
        """Nullify ca_certificate when insecure_skip_tls_verify is True.

        A custom CA is meaningless when TLS verification is disabled entirely.
        """
        if self.insecure_skip_tls_verify and self.ca_certificate is not None:
            self.ca_certificate = None
        return self


class MCPServerConfigurationInput(IntegrationSecurityMixin):
    """Admin-provided fields for MCP server integrations (used by create/patch)."""

    integration_type: Literal["mcp_server"] = "mcp_server"

    base_url: str = Field(description="Base URL for the MCP server", json_schema_extra={"format": "uri"})

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    @model_validator(mode="after")
    def validate_base_url_scheme(self) -> Self:
        """Validate MCP endpoint URL (paths allowed, e.g. /mcp)."""
        self.base_url = validate_endpoint_url(self.base_url, allow_http=self.allow_http)
        return self


class LLMProviderConfiguration(IntegrationSecurityMixin):
    """Configuration for LLM provider integrations."""

    integration_type: Literal["llm_provider"] = "llm_provider"

    provider_hint: LLMProviderHint = Field(
        description="LLM provider backend type",
    )

    base_url: str | None = Field(
        default=None,
        description="Base URL for the LLM provider API. Required for red_hat_ai and custom providers.",
        json_schema_extra={"format": "uri"},
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    @model_validator(mode="after")
    def validate_llm_provider_config(self) -> Self:
        """Validate URL (when present) and require base_url for certain providers."""
        if self.base_url and self.base_url.strip():
            self.base_url = validate_endpoint_url(self.base_url, allow_http=self.allow_http)
        elif not self.base_url or not self.base_url.strip():
            if self.provider_hint in (LLMProviderHint.RED_HAT_AI, LLMProviderHint.CUSTOM):
                msg = f"base_url is required for {self.provider_hint} provider"
                raise ValueError(msg)
            self.base_url = None
        return self


class AAPConfiguration(IntegrationSecurityMixin):
    """Configuration for Ansible Automation Platform integrations."""

    integration_type: Literal["ansible_automation_platform"] = "ansible_automation_platform"

    base_url: str = Field(
        title="AAP URL",
        description="URL of the Ansible Automation Platform",
        json_schema_extra={"format": "uri"},
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]

    @model_validator(mode="after")
    def validate_base_url_scheme(self) -> Self:
        """Validate and normalize URL to prevent SSRF."""
        self.base_url = validate_host_url(self.base_url, allow_http=self.allow_http)
        return self


# Configuration types (used by DB model, read schema, and create/patch)
IntegrationConfigurationTypes = MCPServerConfigurationInput | LLMProviderConfiguration | AAPConfiguration
IntegrationConfiguration = Annotated[
    IntegrationConfigurationTypes,
    Field(discriminator="integration_type"),
]

# Aliases: collapse Input vs Full distinction now that system-managed
# fields (discovered_tools) are stored as separate Tool records.
IntegrationConfigurationInputTypes = IntegrationConfigurationTypes
IntegrationConfigurationInput = IntegrationConfiguration
MCPServerConfiguration = MCPServerConfigurationInput
