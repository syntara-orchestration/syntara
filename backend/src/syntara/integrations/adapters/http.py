"""Connection checks for the HTTP integration."""

from datetime import UTC, datetime
from http import HTTPStatus
from typing import Any

import httpx

from syntara.integrations.adapters.factory import register_health_check_adapter
from syntara.integrations.adapters.protocol import DiscoverResult, HealthCheckErrorType, ValidateResult
from syntara.integrations.models.integration import IntegrationType
from syntara.integrations.models.integration_configuration import HTTPConfiguration


class HTTPAdapter:
    """Check the configured HTTPS origin without following redirects."""

    def __init__(self, configuration: HTTPConfiguration) -> None:
        """Retain the validated HTTPS connection settings."""
        self.configuration = configuration

    async def validate(self, resolved_credential: dict[str, Any], timeout_seconds: int) -> ValidateResult:
        """Check the origin using a bounded HEAD request."""
        checked_at = datetime.now(UTC)
        token = resolved_credential.get("bearer_token")
        if not isinstance(token, str) or not token:
            return ValidateResult(
                success=False,
                checked_at=checked_at,
                error="Bearer credential unavailable",
                error_type=HealthCheckErrorType.AUTH_FAILURE,
            )
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds, follow_redirects=False, trust_env=False) as client:
                response = await client.head(self.configuration.base_url, headers={"Authorization": f"Bearer {token}"})
            success = (
                response.status_code < HTTPStatus.BAD_REQUEST or response.status_code == HTTPStatus.METHOD_NOT_ALLOWED
            )
            return ValidateResult(
                success=success,
                checked_at=checked_at,
                error=None if success else f"HTTP origin returned {response.status_code}",
                error_type=None if success else HealthCheckErrorType.CONNECTION_ERROR,
            )
        except httpx.TransportError:
            return ValidateResult(
                success=False,
                checked_at=checked_at,
                error="HTTP origin connection failed",
                error_type=HealthCheckErrorType.CONNECTION_ERROR,
            )

    async def discover(self, resolved_credential: dict[str, Any], timeout_seconds: int) -> DiscoverResult:
        """Report connection status without discovering resources."""
        result = await self.validate(resolved_credential, timeout_seconds)
        return DiscoverResult(**result.model_dump())


register_health_check_adapter(IntegrationType.HTTP, HTTPAdapter)
