"""Request model for push-button Ansible Automation Platform OIDC identity provider setup."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from syntara.core.lib.url_validation import validate_host_url


class AAPOIDCSetupRequest(BaseModel):
    """Request body for push-button Ansible Automation Platform OIDC identity provider setup."""

    model_config = ConfigDict(extra="forbid")

    aap_url: str = Field(
        min_length=1,
        title="Ansible Automation Platform URL",
        description="Ansible Automation Platform base URL (e.g., https://aap.example.com)",
    )
    organization: str = Field(
        default="Default",
        min_length=1,
        title="Organization",
        description="Ansible Automation Platform organization name to create the OAuth2 application in",
    )
    admin_username: str | None = Field(
        default=None,
        min_length=1,
        title="Platform Admin Username",
        description="Ansible Automation Platform platform admin username (required when using basic auth)",
    )
    admin_password: str | None = Field(
        default=None,
        min_length=1,
        title="Platform Admin Password",
        description="Ansible Automation Platform platform admin password (used only for setup, never stored)",
        json_schema_extra={"format": "password"},
    )
    personal_access_token: str | None = Field(
        default=None,
        min_length=1,
        title="Personal Access Token",
        description=(
            "Ansible Automation Platform personal access token (alternative to username/password, never stored)"
        ),
        json_schema_extra={"format": "password"},
    )
    insecure_skip_tls_verify: bool = Field(
        default=False,
        title="Insecure Skip TLS Verify",
        description="Skip TLS certificate verification for the Ansible Automation Platform connection",
    )

    @field_validator("aap_url")
    @classmethod
    def validate_aap_url(cls, v: str) -> str:
        """Validate and normalize the AAP URL."""
        return validate_host_url(v, allow_http=True)

    @model_validator(mode="after")
    def validate_auth_method(self) -> AAPOIDCSetupRequest:
        """Ensure exactly one authentication method is provided."""
        has_basic = self.admin_username is not None or self.admin_password is not None
        has_token = self.personal_access_token is not None

        if has_basic and has_token:
            msg = "Provide either admin credentials or a personal access token, not both."
            raise ValueError(msg)

        if not has_basic and not has_token:
            msg = "Provide either admin credentials (username and password) or a personal access token."
            raise ValueError(msg)

        if has_basic and (self.admin_username is None or self.admin_password is None):
            msg = "Both admin_username and admin_password are required when using basic auth."
            raise ValueError(msg)

        return self
