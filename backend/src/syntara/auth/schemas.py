"""Request and response schemas for authentication endpoints."""

from pydantic import BaseModel, Field, field_validator

from syntara.core.exceptions import SafeValueError


class LoginRequest(BaseModel):
    """Login request with username and password."""

    username: str = Field(description="Username")
    password: str = Field(description="Password", json_schema_extra={"format": "password"})

    @field_validator("username")
    @classmethod
    def reject_null_bytes(cls, v: str) -> str:
        """Reject null bytes that would cause PostgreSQL CharacterNotInRepertoireError."""
        if "\x00" in v:
            msg = "Username contains invalid characters"
            raise SafeValueError(msg)
        return v


class AccessTokenResponse(BaseModel):
    """Access token response (refresh token is sent via HttpOnly cookie)."""

    access_token: str = Field(description="JWT access token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(description="Access token lifetime in seconds")


class CsrfTokenResponse(BaseModel):
    """CSRF form token response."""

    csrf_token: str = Field(description="CSRF form token for use in X-CSRF-Token header")


class UserInfo(BaseModel):
    """Current user information derived from access token claims."""

    id: str = Field(description="User UUID")
    username: str = Field(description="Username")
    email: str | None = Field(default=None, description="User email")
    groups: list[str] = Field(default_factory=list, description="Group memberships")
    rp_logout_enabled: bool = Field(
        default=False,
        description="Whether RP-initiated logout is enabled for this user's current session",
    )


class AuthProviderInfo(BaseModel):
    """Public identity provider info for the login page."""

    id: str = Field(description="Provider UUID")
    name: str = Field(description="Provider display name")
    provider_type: str = Field(description="Provider type (e.g. oidc)")
    provider_template: str | None = Field(default=None, description="Provider template (e.g. aap)")


class AuthProvidersResponse(BaseModel):
    """Response for the public providers listing endpoint."""

    resources: list[AuthProviderInfo] = Field(default_factory=list, description="Enabled identity providers")


class WebSocketTicketResponse(BaseModel):
    """Response for the WebSocket ticket exchange endpoint."""

    ticket: str = Field(description="Single-use opaque ticket for WebSocket connection")
    expires_in: int = Field(description="Ticket lifetime in seconds")
