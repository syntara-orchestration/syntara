"""Authenticated OpenShift API connectivity check for execution integrations."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import quote

import httpx

from syntara.core.lib.tls_utils import build_integration_httpx_verify
from syntara.integrations.adapters.factory import register_health_check_adapter
from syntara.integrations.adapters.protocol import DiscoverResult, HealthCheckErrorType, ValidateResult
from syntara.integrations.models.integration import IntegrationType

if TYPE_CHECKING:
    from syntara.integrations.models.integration_configuration import OpenShiftConfiguration


class OpenShiftAdapter:
    """Verify that the linked ServiceAccount can list worker pods."""

    def __init__(self, config: OpenShiftConfiguration) -> None:
        """Retain the validated non-secret cluster configuration."""
        self._config = config

    async def validate(self, resolved_credential: dict[str, Any], timeout_seconds: int) -> ValidateResult:
        """Call the namespace-scoped Pods API with the managed bearer token."""
        checked_at = datetime.now(UTC)
        token = resolved_credential.get("bearer_token")
        if not isinstance(token, str) or not token.strip():
            return ValidateResult(
                success=False,
                checked_at=checked_at,
                error="OpenShift bearer token is missing",
                error_type=HealthCheckErrorType.AUTH_FAILURE,
            )
        namespace = quote(self._config.namespace, safe="")
        url = f"{self._config.base_url}/api/v1/namespaces/{namespace}/pods"
        verify = build_integration_httpx_verify(ca_certificate=self._config.ca_certificate)
        try:
            async with httpx.AsyncClient(verify=verify, timeout=timeout_seconds, follow_redirects=False) as client:
                response = await client.get(url, params={"limit": 1}, headers={"Authorization": f"Bearer {token}"})
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            return ValidateResult(
                success=False,
                checked_at=checked_at,
                error=f"OpenShift Pods API returned HTTP {status}",
                error_type=(
                    HealthCheckErrorType.AUTH_FAILURE if status in {401, 403} else HealthCheckErrorType.CONNECTION_ERROR
                ),
            )
        except httpx.TimeoutException:
            return ValidateResult(
                success=False,
                checked_at=checked_at,
                error="OpenShift API connection timed out",
                error_type=HealthCheckErrorType.TIMEOUT,
            )
        except httpx.TransportError:
            return ValidateResult(
                success=False,
                checked_at=checked_at,
                error="Unable to connect to OpenShift API",
                error_type=HealthCheckErrorType.CONNECTION_ERROR,
            )
        return ValidateResult(success=True, checked_at=checked_at)

    async def discover(self, resolved_credential: dict[str, Any], timeout_seconds: int) -> DiscoverResult:
        """OpenShift has no integration-level resources to discover."""
        result = await self.validate(resolved_credential, timeout_seconds)
        return DiscoverResult(
            success=result.success,
            checked_at=result.checked_at,
            error=result.error,
            error_type=result.error_type,
        )


register_health_check_adapter(IntegrationType.OPENSHIFT, lambda c: OpenShiftAdapter(cast("OpenShiftConfiguration", c)))
