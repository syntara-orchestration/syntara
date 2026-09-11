"""Identity provider configuration models.

This module contains configuration classes for different identity provider types.
Each configuration class defines the required and optional parameters for
connecting to and interacting with a specific provider type.
"""

from enum import StrEnum
from typing import Annotated, ClassVar, Literal
from uuid import UUID

import jmespath
from pydantic import ConfigDict, Field, HttpUrl, ValidationError, field_validator, model_validator
from pydantic_core.core_schema import ValidationInfo, ValidatorFunctionWrapHandler
from sqlmodel import SQLModel

from syntara.core.config.base import get_settings
from syntara.core.lib.consumer_configuration import BaseConsumerConfiguration


class OIDCIdpType(StrEnum):
    """Known OIDC identity provider types for pre-configured UI defaults."""

    AAP = "aap"
    CUSTOM = "custom"


class OIDCClaimMapping(SQLModel):
    """Maps Orchestrator user fields to IdP-specific OIDC claim names."""

    subject: str = Field(default="sub")
    email: str = Field(default="email")
    username: str = Field(default="preferred_username")
    first_name: str = Field(default="given_name")
    last_name: str = Field(default="family_name")

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]


class OIDCGroupMappingEntry(SQLModel):
    """API-facing schema for a single IdP-to-Orchestrator group mapping entry.

    Used in API requests/responses. Actual storage is in the
    ``idp_group_mapping_entries`` table.
    """

    idp_group_value: str = Field(min_length=1, description="Group value from the IdP token (e.g. GUID or role name)")
    mapped_group_id: UUID = Field(description="ID of the group to map to")

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="forbid")  # type: ignore[assignment]


def _validate_jmespath(v: str | None) -> str | None:
    """Validate a JMESPath expression, returning it unchanged or raising ValueError."""
    if v is None:
        return v
    try:
        jmespath.compile(v)
    except jmespath.exceptions.JMESPathError as e:
        msg = f"Invalid group extraction expression: '{v}' is not a valid JMESPath expression"
        raise ValueError(msg) from e
    return v


def _validate_idp_type(v: str | None) -> str | None:
    """Validate idp_type against known provider types."""
    if v is None:
        return v
    known = {e.value for e in OIDCIdpType}
    if v not in known:
        msg = f"Unknown idp_type '{v}'. Known values: {', '.join(sorted(known))}"
        raise ValueError(msg)
    return v


def _allow_http() -> bool:
    """Return whether HTTP URLs are allowed based on OIDC network policy."""
    # False (production): only https:// URLs accepted
    # True (dev/internal): http:// also accepted
    return get_settings().oidc_allow_private_networks


def _validate_url_format(url: str | None, handler: ValidatorFunctionWrapHandler, field_name: str | None) -> str | None:
    """Enforce URL format and HTTPS scheme (unless dev mode)."""
    if url is None:
        return None
    try:
        parsed: HttpUrl = handler(url)
    except ValidationError as err:
        msg = f"{field_name} must be a valid URL"
        raise ValueError(msg) from err
    if field_name != "redirect_uri" and not _allow_http() and parsed.scheme == "http":
        msg = f"{field_name} must use HTTPS"
        raise ValueError(msg)
    return str(parsed)


_OIDC_DEFAULT_SCOPES = "openid profile email"
_OIDC_AUTO_DISCOVERY_DESC = "Use OIDC auto-discovery via .well-known endpoint"
_OIDC_ISSUER_URL_DESC = "OIDC issuer URL (e.g. https://accounts.google.com)"
_OIDC_CLIENT_ID_DESC = "OAuth 2.0 client ID"
_OIDC_REDIRECT_URI_DESC = "OAuth 2.0 redirect URI"
_OIDC_SCOPES_DESC = "Space-separated list of OAuth 2.0 scopes"
_OIDC_AUTHORIZATION_ENDPOINT_DESC = "Authorization endpoint URL"
_OIDC_TOKEN_ENDPOINT_DESC = "Token endpoint URL"  # noqa: S105
_OIDC_JWKS_URI_DESC = "JWKS URI for token verification"
_OIDC_USERINFO_ENDPOINT_DESC = "Userinfo endpoint URL (optional)"


class OIDCConfiguration(BaseConsumerConfiguration):
    """Configuration for OIDC (OpenID Connect) providers."""

    provider_type: Literal["oidc"] = "oidc"

    idp_type: str | None = Field(
        default=None,
        description=f"Identity provider type hint. Known values: {', '.join(v.value for v in OIDCIdpType)}",
    )

    auto_discovery: bool = Field(default=True, description=_OIDC_AUTO_DISCOVERY_DESC)

    issuer_url: HttpUrl = Field(description=_OIDC_ISSUER_URL_DESC)

    client_id: str = Field(description=_OIDC_CLIENT_ID_DESC)

    client_secret: str | None = Field(default=None, description="OAuth 2.0 client secret")

    redirect_uri: HttpUrl = Field(description=_OIDC_REDIRECT_URI_DESC)

    scopes: str = Field(default=_OIDC_DEFAULT_SCOPES, description=_OIDC_SCOPES_DESC)

    # Manual endpoint fields (used when auto_discovery is disabled)
    authorization_endpoint: HttpUrl | None = Field(default=None, description=_OIDC_AUTHORIZATION_ENDPOINT_DESC)
    token_endpoint: HttpUrl | None = Field(default=None, description=_OIDC_TOKEN_ENDPOINT_DESC)
    jwks_uri: HttpUrl | None = Field(default=None, description=_OIDC_JWKS_URI_DESC)
    userinfo_endpoint: HttpUrl | None = Field(default=None, description=_OIDC_USERINFO_ENDPOINT_DESC)
    end_session_endpoint: HttpUrl | None = Field(
        default=None, description="OIDC end session endpoint URL for RP-initiated logout"
    )

    # RP-initiated logout configuration
    enable_rp_initiated_logout: bool = Field(
        default=False,
        description="Enable RP-initiated logout redirect to IdP when user logs out",
    )

    claim_mapping: OIDCClaimMapping = Field(default_factory=OIDCClaimMapping)

    # Group mapping — jmespath_expression is persisted in JSONB;
    # group_mapping_entries is a pass-through stored in the idp_group_mapping_entries table.
    group_jmespath_expression: str | None = Field(
        default=None, description="JMESPath expression to extract group values from token claims"
    )
    group_mapping_entries: list[OIDCGroupMappingEntry] = Field(
        default_factory=list,
        exclude=True,
        description="IdP-to-Orchestrator group mapping entries",
    )
    allow_all_authenticated: bool = Field(
        default=False, description="Allow all users from this IdP to log in regardless of group mapping results"
    )
    aap_role_mapping_enabled: bool = Field(
        default=False,
        description="Map Ansible Automation Platform aap_system_role claim to built-in groups",
    )
    disable_tls_verify: bool = Field(
        default=False,
        description="Disable TLS certificate verification for requests to this identity provider (insecure)",
    )

    @field_validator(
        "issuer_url",
        "redirect_uri",
        "authorization_endpoint",
        "token_endpoint",
        "jwks_uri",
        "userinfo_endpoint",
        "end_session_endpoint",
        mode="wrap",
    )
    @classmethod
    def validate_oidc_configuration_url(
        cls, v: str | None, handler: ValidatorFunctionWrapHandler, info: ValidationInfo
    ) -> str | None:
        """Enforce URL format and HTTPS scheme (unless dev mode)."""
        return _validate_url_format(v, handler, info.field_name)

    @field_validator("idp_type")
    @classmethod
    def validate_idp_type(cls, v: str | None) -> str | None:
        """Validate idp_type against known provider types."""
        return _validate_idp_type(v)

    @field_validator("group_jmespath_expression")
    @classmethod
    def validate_group_jmespath_expression(cls, v: str | None) -> str | None:
        """Reject syntactically invalid JMESPath expressions at configuration time."""
        return _validate_jmespath(v)

    @model_validator(mode="after")
    def validate_aap_role_mapping_requires_aap_type(self) -> "OIDCConfiguration":
        """Reject aap_role_mapping_enabled on non-AAP identity providers."""
        if self.aap_role_mapping_enabled and self.idp_type != OIDCIdpType.AAP:
            msg = "aap_role_mapping_enabled requires idp_type to be 'aap'"
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_manual_endpoint_fields(self) -> "OIDCConfiguration":
        """Validate manual endpoints are present when auto_discovery is disabled."""
        if not self.auto_discovery:
            required = {
                "token_endpoint": self.token_endpoint,
                "authorization_endpoint": self.authorization_endpoint,
                "jwks_uri": self.jwks_uri,
            }
            for name, value in required.items():
                if not value:
                    msg = f"{name} is required when auto_discovery is disabled"
                    raise ValueError(msg)
        return self

    @classmethod
    def sensitive_fields(cls) -> frozenset[str]:
        """Declare client_secret as a sensitive field for SecretService encryption."""
        return frozenset({"client_secret"})


class OIDCConfigurationResponse(SQLModel):
    """Response schema for OIDC configuration (excludes client_secret)."""

    provider_type: Literal["oidc"] = "oidc"

    idp_type: str | None = Field(default=None, description="Identity provider type hint")

    auto_discovery: bool = Field(default=True, description=_OIDC_AUTO_DISCOVERY_DESC)

    issuer_url: HttpUrl = Field(description=_OIDC_ISSUER_URL_DESC)

    client_id: str = Field(description=_OIDC_CLIENT_ID_DESC)

    redirect_uri: HttpUrl = Field(description=_OIDC_REDIRECT_URI_DESC)

    scopes: str = Field(default=_OIDC_DEFAULT_SCOPES, description=_OIDC_SCOPES_DESC)

    authorization_endpoint: HttpUrl | None = Field(default=None, description=_OIDC_AUTHORIZATION_ENDPOINT_DESC)
    token_endpoint: HttpUrl | None = Field(default=None, description=_OIDC_TOKEN_ENDPOINT_DESC)
    jwks_uri: HttpUrl | None = Field(default=None, description=_OIDC_JWKS_URI_DESC)
    userinfo_endpoint: HttpUrl | None = Field(default=None, description=_OIDC_USERINFO_ENDPOINT_DESC)
    end_session_endpoint: HttpUrl | None = Field(
        default=None, description="OIDC end session endpoint URL for RP-initiated logout"
    )

    enable_rp_initiated_logout: bool = Field(
        default=False,
        description="Enable RP-initiated logout redirect to IdP when user logs out",
    )

    claim_mapping: OIDCClaimMapping = Field(default_factory=OIDCClaimMapping)
    group_jmespath_expression: str | None = Field(default=None, description="JMESPath expression for group extraction")
    group_mapping_entries: list[OIDCGroupMappingEntry] = Field(
        default_factory=list, description="IdP-to-Orchestrator group mapping entries"
    )
    allow_all_authenticated: bool = Field(
        default=False, description="Allow all users from this IdP to log in regardless of group mapping results"
    )
    aap_role_mapping_enabled: bool = Field(
        default=False,
        description="Map Ansible Automation Platform aap_system_role claim to built-in groups",
    )
    disable_tls_verify: bool = Field(
        default=False,
        description="Disable TLS certificate verification for requests to this identity provider (insecure)",
    )

    model_config: ClassVar[ConfigDict] = ConfigDict(
        extra="forbid",
    )  # type: ignore[assignment]


# Discriminated union for all identity provider configurations
# When adding new provider types (LDAP, SAML), add them to this union
IdentityProviderConfigurationTypes = OIDCConfiguration
IdentityProviderConfiguration = Annotated[
    IdentityProviderConfigurationTypes,
    Field(discriminator="provider_type"),
]


class OIDCConfigurationUpdate(BaseConsumerConfiguration):
    """Update schema for OIDC configuration (client_secret optional — preserves existing if omitted)."""

    provider_type: Literal["oidc"] = "oidc"

    idp_type: str | None = Field(
        default=None,
        description=f"Identity provider type hint. Known values: {', '.join(v.value for v in OIDCIdpType)}",
    )

    auto_discovery: bool = Field(default=True, description=_OIDC_AUTO_DISCOVERY_DESC)

    issuer_url: HttpUrl = Field(description=_OIDC_ISSUER_URL_DESC)

    client_id: str = Field(description=_OIDC_CLIENT_ID_DESC)

    client_secret: str | None = Field(default=None, description="OAuth 2.0 client secret (omit to keep existing)")

    redirect_uri: HttpUrl = Field(description=_OIDC_REDIRECT_URI_DESC)

    scopes: str = Field(default=_OIDC_DEFAULT_SCOPES, description=_OIDC_SCOPES_DESC)

    authorization_endpoint: HttpUrl | None = Field(default=None, description=_OIDC_AUTHORIZATION_ENDPOINT_DESC)
    token_endpoint: HttpUrl | None = Field(default=None, description=_OIDC_TOKEN_ENDPOINT_DESC)
    jwks_uri: HttpUrl | None = Field(default=None, description=_OIDC_JWKS_URI_DESC)
    userinfo_endpoint: HttpUrl | None = Field(default=None, description=_OIDC_USERINFO_ENDPOINT_DESC)
    end_session_endpoint: HttpUrl | None = Field(
        default=None, description="OIDC end session endpoint URL for RP-initiated logout (omit to keep existing)"
    )

    enable_rp_initiated_logout: bool | None = Field(
        default=None,
        description="Enable RP-initiated logout redirect to IdP when user logs out (omit to keep existing)",
    )

    claim_mapping: OIDCClaimMapping | None = Field(
        default=None, description="OIDC claim mapping (omit to keep existing)"
    )
    group_jmespath_expression: str | None = Field(
        default=None, description="JMESPath expression for group extraction (omit to keep existing)"
    )
    group_mapping_entries: list[OIDCGroupMappingEntry] | None = Field(
        default=None,
        exclude=True,
        description="IdP-to-Orchestrator group mapping entries (omit to keep existing)",
    )
    allow_all_authenticated: bool | None = Field(
        default=None,
        description=(
            "Allow all users from this IdP to log in regardless of group mapping results (omit to keep existing)"
        ),
    )
    aap_role_mapping_enabled: bool | None = Field(
        default=None,
        description="Map Ansible Automation Platform aap_system_role claim to built-in groups (omit to keep existing)",
    )
    disable_tls_verify: bool | None = Field(
        default=None,
        description="Disable TLS certificate verification for this identity provider (omit to keep existing)",
    )

    @field_validator(
        "issuer_url",
        "redirect_uri",
        "authorization_endpoint",
        "token_endpoint",
        "jwks_uri",
        "userinfo_endpoint",
        "end_session_endpoint",
        mode="wrap",
    )
    @classmethod
    def validate_oidc_configuration_url(
        cls, v: str | None, handler: ValidatorFunctionWrapHandler, info: ValidationInfo
    ) -> str | None:
        """Enforce URL format and HTTPS scheme (unless dev mode)."""
        return _validate_url_format(v, handler, info.field_name)

    @field_validator("idp_type")
    @classmethod
    def validate_idp_type(cls, v: str | None) -> str | None:
        """Validate idp_type against known provider types."""
        return _validate_idp_type(v)

    @field_validator("group_jmespath_expression")
    @classmethod
    def validate_group_jmespath_expression(cls, v: str | None) -> str | None:
        """Reject syntactically invalid JMESPath expressions at configuration time."""
        return _validate_jmespath(v)

    @classmethod
    def sensitive_fields(cls) -> frozenset[str]:
        """Declare client_secret as a sensitive field for SecretService encryption."""
        return frozenset({"client_secret"})


IdentityProviderConfigurationUpdateTypes = OIDCConfigurationUpdate
IdentityProviderConfigurationUpdate = Annotated[
    IdentityProviderConfigurationUpdateTypes,
    Field(discriminator="provider_type"),
]

IdentityProviderConfigurationResponseTypes = OIDCConfigurationResponse
IdentityProviderConfigurationResponse = Annotated[
    IdentityProviderConfigurationResponseTypes,
    Field(discriminator="provider_type"),
]
