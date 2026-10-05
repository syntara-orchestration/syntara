"""Adapter protocol and result types for integration validation and discovery."""

from __future__ import annotations

from collections.abc import Sequence  # noqa: TC003 — runtime import for classify_http_error
from datetime import datetime  # noqa: TC003 — runtime import required by SQLModel field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from typing import Any

from httpx import HTTPStatusError, Response, codes
from sqlmodel import SQLModel


class HealthCheckErrorType(StrEnum):
    """Classification of health check failures."""

    AUTH_FAILURE = "auth_failure"
    AUTHORIZATION_FAILURE = "authorization_failure"
    TOKEN_EXPIRED = "token_expired"  # noqa: S105
    CONNECTION_ERROR = "connection_error"
    RATE_LIMIT = "rate_limit"
    SSL_ERROR = "ssl_error"
    TIMEOUT = "timeout"


class DiscoveredLLMModel(SQLModel):
    """A model discovered from an LLM provider."""

    id: str
    name: str
    description: str | None = None


class DiscoveredToolParameter(SQLModel):
    """A parameter belonging to a discovered tool."""

    name: str
    type: str = "string"
    description: str = ""
    required: bool = False


class DiscoveredTool(SQLModel):
    """A tool discovered from an MCP server.

    Carries parameter information so that _sync_mcp_tools() can do a full
    upsert without re-fetching from MCP.
    """

    name: str
    description: str | None = None
    parameters: list[DiscoveredToolParameter] | None = None


class ValidateResult(SQLModel):
    """Result of a lightweight connectivity ping (validate endpoint).

    Contains only connection-health fields. No resource discovery fields.
    """

    success: bool
    checked_at: datetime
    error: str | None = None
    error_type: HealthCheckErrorType | None = None


class DiscoverResult(SQLModel):
    """Result of a resource-discovery operation (discover endpoint).

    Returned by the unsaved-connection test (POST /integrations/discover)
    and used internally by refresh_resources() to drive tool sync.
    """

    success: bool
    checked_at: datetime
    error: str | None = None
    error_type: HealthCheckErrorType | None = None
    discovered_tools: list[DiscoveredTool] | None = None
    discovered_models: list[DiscoveredLLMModel] | None = None


def _response_body_suggests_expired_token(response: Response) -> bool:
    """Best-effort detection of expired-token wording in an HTTP error body."""
    try:
        text = response.text.lower()
    except Exception:  # noqa: BLE001 — best-effort body inspection
        return False
    return any(marker in text for marker in ("expired", "token has expired", "token is expired", "jwt expired"))


def classify_http_error(
    errors: Sequence[BaseException],
) -> tuple[HealthCheckErrorType, str]:
    """Classify HTTP status errors into distinct failure categories.

    Shared by all adapter implementations. Iterates errors and returns
    TOKEN_EXPIRED / AUTH_FAILURE for 401, AUTHORIZATION_FAILURE for 403,
    RATE_LIMIT for 429, CONNECTION_ERROR for other HTTP statuses.
    """
    # Guard against empty errors list (defensive programming for error handling code)
    if not errors:
        return (HealthCheckErrorType.CONNECTION_ERROR, "Request failed: unknown")

    # Find first HTTP status error
    for error in errors:
        if isinstance(error, HTTPStatusError):
            status = error.response.status_code

            # Map specific status codes to error types and messages
            if status == codes.UNAUTHORIZED:
                if _response_body_suggests_expired_token(error.response):
                    error_type = HealthCheckErrorType.TOKEN_EXPIRED
                    message = f"Token expired: HTTP {status}"
                else:
                    error_type = HealthCheckErrorType.AUTH_FAILURE
                    message = f"Authentication failed: HTTP {status}"
            elif status == codes.FORBIDDEN:
                error_type = HealthCheckErrorType.AUTHORIZATION_FAILURE
                message = f"Authorization failed: HTTP {status}"
            elif status == codes.TOO_MANY_REQUESTS:
                error_type = HealthCheckErrorType.RATE_LIMIT
                message = f"Rate limit exceeded: HTTP {status}"
            elif status == codes.METHOD_NOT_ALLOWED:
                error_type = HealthCheckErrorType.CONNECTION_ERROR
                message = f"Method not allowed: HTTP {status}"
            elif status == codes.NOT_FOUND:
                error_type = HealthCheckErrorType.CONNECTION_ERROR
                message = f"Endpoint not found: HTTP {status}"
            else:
                error_type = HealthCheckErrorType.CONNECTION_ERROR
                message = f"HTTP error: {status}"

            return (error_type, message)

    # No HTTP status error found
    return (
        HealthCheckErrorType.CONNECTION_ERROR,
        f"Request failed: {type(errors[0]).__name__}" if errors else "HTTP error: unknown",
    )


@runtime_checkable
class IntegrationAdapter(Protocol):
    """Protocol for integration adapters.

    Each integration type (LLM, MCP, Ansible Automation Platform) implements this protocol.
    The adapter receives its typed configuration via the constructor; the
    validate and discover methods only take per-call parameters.

    The resolved_credential parameter is the extra_vars dict produced by
    InjectorResolver.resolve() — not the raw secret dict from SecretService.
    The service layer performs both decryption and injector resolution before
    calling the adapter.
    """

    async def validate(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> ValidateResult:
        """Run a lightweight connectivity ping against the external service."""
        ...

    async def discover(
        self,
        resolved_credential: dict[str, Any],
        timeout_seconds: int,
    ) -> DiscoverResult:
        """Discover resources (tools, models) from the external service."""
        ...
