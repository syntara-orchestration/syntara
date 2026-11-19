"""Validate an OpenShift integration without accessing workloads or pods."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import httpx

from syntara.core.lib.tls_utils import build_integration_httpx_verify
from syntara.integrations.adapters.factory import register_health_check_adapter
from syntara.integrations.adapters.protocol import DiscoverResult, HealthCheckErrorType, ValidateResult
from syntara.integrations.models.integration import IntegrationType

if TYPE_CHECKING:
    from syntara.integrations.models.integration_configuration import OpenShiftConfiguration

_SELF_SUBJECT_REVIEW_PATH = "/apis/authentication.k8s.io/v1/selfsubjectreviews"
_SELF_SUBJECT_REVIEW = {"apiVersion": "authentication.k8s.io/v1", "kind": "SelfSubjectReview"}
_OPENSHIFT_CREDENTIAL_KEY = "bearer_token"


class OpenShiftAdapter:
    """Check API reachability and bearer identity; never access namespace resources."""

    def __init__(self, config: OpenShiftConfiguration) -> None:
        """Retain validated, non-secret cluster configuration."""
        self._config = config

    async def validate(self, resolved_credential: dict[str, Any], timeout_seconds: int) -> ValidateResult:
        """Ask the API server to identify the bearer token without creating a persisted resource."""
        checked_at = datetime.now(UTC)
        token = resolved_credential.get(_OPENSHIFT_CREDENTIAL_KEY)
        if not isinstance(token, str) or not token.strip():
            return ValidateResult(
                success=False,
                checked_at=checked_at,
                error="OpenShift bearer token is missing",
                error_type=HealthCheckErrorType.AUTH_FAILURE,
            )

        try:
            async with httpx.AsyncClient(
                verify=build_integration_httpx_verify(ca_certificate=self._config.ca_certificate),
                timeout=timeout_seconds,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    f"{self._config.base_url}{_SELF_SUBJECT_REVIEW_PATH}",
                    json=_SELF_SUBJECT_REVIEW,
                    headers={"Authorization": f"Bearer {token}"},
                )
                response.raise_for_status()
                user_info = response.json().get("status", {}).get("userInfo", {})
                username = user_info.get("username") if isinstance(user_info, dict) else None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            return ValidateResult(
                success=False,
                checked_at=checked_at,
                error=f"OpenShift authentication API returned HTTP {status}",
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
        except (TypeError, ValueError, AttributeError):
            return ValidateResult(
                success=False,
                checked_at=checked_at,
                error="OpenShift authentication API returned an invalid response",
                error_type=HealthCheckErrorType.CONNECTION_ERROR,
            )
        authenticated = isinstance(username, str) and bool(username) and username != "system:anonymous"
        return ValidateResult(
            success=authenticated,
            checked_at=checked_at,
            error=None if authenticated else "OpenShift did not confirm an authenticated identity",
            error_type=None if authenticated else HealthCheckErrorType.AUTH_FAILURE,
        )

    async def discover(self, resolved_credential: dict[str, Any], timeout_seconds: int) -> DiscoverResult:
        """Expose the same connection check; no cluster resources are discovered."""
        result = await self.validate(resolved_credential, timeout_seconds)
        return DiscoverResult(
            success=result.success,
            checked_at=result.checked_at,
            error=result.error,
            error_type=result.error_type,
        )


register_health_check_adapter(IntegrationType.OPENSHIFT, lambda c: OpenShiftAdapter(cast("OpenShiftConfiguration", c)))
